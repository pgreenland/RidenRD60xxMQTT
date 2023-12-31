from typing import Dict, Optional, Tuple
import asyncio
import json
import logging
import signal
import time

import aiomqtt

from rd60xx import RD60xx
from bridge import Bridge
from psu_state import PSUStates

class RD60xxToMQTT:
    """Remote control Riden RD60xx PSU's via MQTT"""

    def __init__(self,
                 hostname:str,
                 port:int,
                 client_id:Optional[str]=None,
                 username:Optional[str]=None,
                 password:Optional[str]=None,
                 ca_cert:Optional[str]=None,
                 client_cert:Optional[str]=None,
                 client_key:Optional[str]=None,
                 insecure:bool=False,
                 mqtt_base_topic:str="riden_psu",
                 psu_identity_to_name:Dict[str, str]={},
                 ip_to_identity_cache_timeout_secs:int=21600,
                 mqtt_reconnect_delay_secs:int=5,
                 set_clock_on_connection:bool=True) -> None:
        """Constructor"""

        # Store args
        self._hostname = hostname
        self._port = port
        self._client_id = client_id
        self._username = username
        self._password = password
        self._ca_cert = ca_cert
        self._client_cert = client_cert
        self._client_key = client_key
        self._insecure = insecure
        self._mqtt_base_topic = mqtt_base_topic
        self._psu_identity_to_name = psu_identity_to_name
        self._ip_to_identity_cache_timeout_secs = ip_to_identity_cache_timeout_secs
        self._mqtt_reconnect_delay_secs = mqtt_reconnect_delay_secs
        self._set_clock_on_connection = set_clock_on_connection

        # Retrieve logger
        self._logger = logging.getLogger("RD60xxToMQTT")

        # Create shutdown event
        self._shutdown_event = asyncio.Event()

        # Newly connected PSUs
        self._new_psu_queue = asyncio.Queue(maxsize=16)

        # Persistent state (data assoicated with PSU thats persisted across unit connections)
        self._psu_states = PSUStates()

        # Map of connected PSUs (serial no -> rd60xxmqtt instances)
        self._psus = {}

        # Reset MQTT client
        self._mqtt_client = None

    async def run(self):
        """Run service"""

        # Retreive event loop
        loop = asyncio.get_event_loop()

        # Register the signal handler
        for signame in ['SIGINT', 'SIGTERM']:
            loop.add_signal_handler(getattr(signal, signame), lambda: asyncio.create_task(self._handle_signal(signame)))

        # Create TCP server, waiting for PSU clients to connect
        psu_server = await loop.create_server(
            lambda: RD60xx(self.psu_connected,
                           self.psu_disconnected,
                           close_comm_on_error=True),
            '0.0.0.0', 8080
        )

        # Create task to manage MQTT connection and process inbound messages
        mqtt_task = loop.create_task(self._mqtt_inbound())

        # Create task to on-board new PSUs (as we cant execute async functions in the non-async callback)
        psu_task = loop.create_task(self._psu_task())

        # Wait for shutdown signal
        await self._shutdown_event.wait()
        self._logger.info("Stopping...")

        # Stop tasks
        mqtt_task.cancel()
        psu_server.close()
        psu_task.cancel()
        for _, psu in self._psus.items():
            psu.cancel()
        self._psus.clear()

        # All done
        self._logger.info("Bye")

    async def _handle_signal(self, signal_name:str):
        """Handle OS signal"""

        # Log signal and set shutdown event
        self._logger.debug(f"Received {signal_name}")
        self._shutdown_event.set()

    def psu_connected(self, client, transport):
        """Handle new client connecting"""

        # Retrieve PSU IP and port
        host, port = transport.get_extra_info('peername')

        # Yey
        self._logger.info("PSU connected (%s:%d)", host, port)

        try:
            # Queue PSU for interrogation
            self._new_psu_queue.put_nowait((client, host, port))

        except asyncio.QueueFull:
            # Disconnect client
            client.close()

    def psu_disconnected(self, client):
        """Handle client disconnecting"""

        # Reset host and port
        host_port = "0.0.0.0:0"

        # Iterate over PSUs
        for identity, psu in self._psus.items():
            if client == psu.client:
                # Found PSU, retrieve host and port
                host_port = psu.host_port

                # Cancel PSU background task
                self._psus[identity].cancel()

                # Remove from dictionary
                del self._psus[identity]
                break

        # Aww
        self._logger.info("PSU disconnected (%s)", host_port)

    async def _mqtt_inbound(self):
        """Connect and reconnect to MQTT broker as required, subscribing to and reading messages"""

        # Entry
        self._logger.info("MQTT task running")

        while True:
            try:
                # Create TLS params
                tls_params = None
                tls_insecure = None
                if (self._ca_cert is not None or (self._client_cert is not None and self._client_key is not None)):
                    tls_params = aiomqtt.TLSParameters(self._ca_cert, self._client_cert, self._client_key)
                    tls_insecure = self._insecure

                # Construct client
                async with aiomqtt.Client(hostname=self._hostname, port=self._port,
                                          username=self._username, password=self._password,
                                          tls_params=tls_params,
                                          tls_insecure=tls_insecure,
                                          client_id=self._client_id) as client:
                    # Yey
                    self._logger.info("MQTT connected!")

                    # Make client available to psu connection handler
                    self._mqtt_client = client

                    # Subscribe to PSU topics
                    await client.subscribe(f"{self._mqtt_base_topic}/psu/list/get", qos=0)
                    await client.subscribe(f"{self._mqtt_base_topic}/psu/+/state/get", qos=0)
                    await client.subscribe(f"{self._mqtt_base_topic}/psu/+/state/set", qos=2)

                    # Prepare wildcards
                    wildcard_psus_get = f"{self._mqtt_base_topic}/psu/list/get"
                    wildcard_state_get = f"{self._mqtt_base_topic}/psu/+/state/get"
                    wildcard_state_set = f"{self._mqtt_base_topic}/psu/+/state/set"

                    # Retrive messages
                    async with client.messages() as messages:
                        # Process messages, dispatching them to appropriate PSU instances
                        async for message in messages:
                            # Attempt to de-serialize message
                            try:
                                payload = json.loads(message.payload)
                            except:
                                payload = None

                            # Extract identity from topic
                            topic = message.topic.value[len(f"{self._mqtt_base_topic}/"):]
                            identity = topic.split("/")[1]

                            # Lookup PSU
                            psu:Bridge = self._psus.get(identity)

                            # Log msg
                            self._logger.debug("Msg arrived on topic: '%s', for identity: '%s' with payload: '%s'", topic, identity, repr(payload))

                            # Act on topics
                            if message.topic.matches(wildcard_state_set) and not payload is None:
                                # Set state request, retrieve state for PSU
                                state = self._psu_states.get_state(identity, create=False)

                                # Handle period first
                                if type(payload.get("period")) in (int, float) and state is not None:
                                    # Retrieve and limit period
                                    update_period = payload["period"]
                                    if update_period != 0:
                                        # Limit to 100ms updates
                                        update_period = max(update_period, 0.1)

                                    # Set new update period
                                    self._logger.debug("Update identity %s period to %d", identity, update_period)
                                    state.update_period = update_period

                                # Pass request to PSU if connected
                                if psu is not None:
                                    self._logger.debug("Set identity %s state to %s", identity, repr(payload))
                                    psu.queue_state_set(payload)

                            elif message.topic.matches(wildcard_state_get):
                                # Get state request, check if we should query the unit
                                if not payload is None and payload.get("query", False) and psu is not None:
                                    # We should query the unit and we can
                                    self._logger.debug("Get identity %s state with query", identity)
                                    psu.queue_state_get()

                                else:
                                    # Nope, just checking if the unit is connected, or attempting to query it but its not connected
                                    resp = {}
                                    resp["connected"] = (psu is not None)
                                    state = self._psu_states.get_state(identity, create=False)
                                    resp["period"] = (state.update_period if state is not None else 0)
                                    self._logger.debug("Get identity %s state without query", identity)
                                    await self._mqtt_outbound(identity, resp)

                            elif message.topic.matches(wildcard_psus_get):
                                # Send PSU list
                                self._logger.debug("Get psu list")
                                await self._send_psu_list()

            except aiomqtt.MqttError as error:
                # MQTT connection failed
                self._mqtt_client = None
                self._logger.warning("MQTT error %s, reconnecting in %d seconds.", error, self._mqtt_reconnect_delay_secs)
                await asyncio.sleep(self._mqtt_reconnect_delay_secs)

            except asyncio.CancelledError:
                # Task cancelled
                self._logger.info("MQTT task stopped")

                # Reset client
                self._mqtt_client = None
                break

            except:
                # Catchall
                self._mqtt_client = None
                self._logger.exception("General error, reconnecting in %d seconds.", self._mqtt_reconnect_delay_secs)
                await asyncio.sleep(self._mqtt_reconnect_delay_secs)

    async def _mqtt_outbound(self, identity:str, state:dict):
        """Send MQTT state message on behalf of caller"""

        if self._mqtt_client:
            # Publish message
            try:
                topic = f"{self._mqtt_base_topic}/psu/{identity}/state"
                self._logger.debug("Msg leaving on topic: '%s', for identity: '%s' with payload: '%s'", topic, identity, repr(state))
                await self._mqtt_client.publish(topic, payload=json.dumps(state))
            except aiomqtt.MqttError:
                # Ignore MQTT errors
                pass

    async def _psu_task(self):
        """Handle newly connected PSUs"""

        # Entry
        self._logger.info("PSU task running")

        # Map of IP -> PSU identity / connection time
        identity_cache:Dict[str, Tuple[str, int]] = {}

        try:
            # Retireve PSUs from queue
            while True:
                # Fetch newly connected PSU
                psu, host, port = await self._new_psu_queue.get()

                # Lookup identity from IP
                identity, last_connection = identity_cache.get(host, (None, None))

                # Retrieve time
                time_now = time.monotonic()

                if identity is not None:
                    # Identity found, calculate elapsed time between now and when PSU last connected
                    time_diff = time_now - last_connection

                    # Check against limit
                    if time_diff > self._ip_to_identity_cache_timeout_secs:
                        # PSU has been offline for longer than cache limit, force re-query
                        identity = None
                        last_connection = None

                if identity is None:
                    # Query PSU to retrieve model and serial number (forming identity)
                    query_result = await psu.get_state()

                    if query_result is None:
                        # Query failed, close connection
                        psu.close()
                        continue

                    # Retrieve model and serial number from query result
                    model = query_result.model
                    serial_no = query_result.serial_no

                    # Generate identity, combining model and serial number for cases where a user has
                    # multiple series of PSU with overlapping serial number ranges
                    identity = f"{model}_{serial_no}"

                # Update last connection time
                last_connection = time_now

                # Update identity map
                identity_cache[host] = (identity, last_connection)

                # Lookup name
                name = self._psu_identity_to_name.get(identity, "Unnamed")

                # Log identity
                self._logger.info("PSU %s:%d's identity is %s, it's name is '%s'", host, port, identity, name)

                # Retrieve PSU state object based on identity
                state = self._psu_states.get_state(identity)

                # Create new bridge instance
                psu_bridge = Bridge(host, port, identity, model, serial_no, psu, state, self._mqtt_outbound, self._set_clock_on_connection)

                # Add bridge instance to map
                self._psus[identity] = psu_bridge

                # Send updated PSU list
                await self._send_psu_list()

        except asyncio.CancelledError:
            # Task cancelled
            self._logger.info("PSU task stopped")

    async def _send_psu_list(self) -> None:
        """Transmit PSU list over MQTT"""

        # Reset list of names and identities
        psu_name_ident = []

        for identity, psu in self._psus.items():
            name = self._psu_identity_to_name.get(identity, "Unnamed")
            psu_name_ident.append({"identity" : identity, "name" : name, "model" : psu.model, "serial_no" : psu.serial_no})

        if self._mqtt_client:
            try:
                await self._mqtt_client.publish(f"{self._mqtt_base_topic}/psu/list", payload=json.dumps(psu_name_ident))
            except aiomqtt.MqttError:
                # Ignore MQTT errors
                pass
