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
                 set_clock_on_connection:bool=True,
                 default_update_period:float=0,
                 mqtt_discovery_enabled:bool=False,
                 mqtt_discovery_prefix:str=None) -> None:
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
        self._default_update_period = default_update_period
        self._mqtt_discovery_enabled = mqtt_discovery_enabled
        self._mqtt_discovery_prefix = mqtt_discovery_prefix

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

        # Track which PSUs have had their firmware version updated in discovery
        self._firmware_version_updated = set()

        # Track which PSUs have pending state queries (for rate limiting)
        self._pending_state_queries = set()

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

                # Clear firmware version update flag so it updates on reconnect
                self._firmware_version_updated.discard(identity)
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

                # Prepare availability topic and LWT message
                availability_topic = f"{self._mqtt_base_topic}/bridge/status"
                will_message = aiomqtt.Will(topic=availability_topic, payload="offline", qos=1, retain=True)

                # Construct client with LWT
                async with aiomqtt.Client(hostname=self._hostname, port=self._port,
                                          username=self._username, password=self._password,
                                          tls_params=tls_params,
                                          tls_insecure=tls_insecure,
                                          client_id=self._client_id,
                                          will=will_message) as client:
                    # Yey
                    self._logger.info("MQTT connected!")

                    # Make client available to psu connection handler
                    self._mqtt_client = client

                    # Publish online status (will be replaced by LWT "offline" on disconnect)
                    await client.publish(availability_topic, payload="online", qos=1, retain=True)

                    try:
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

                                        # Check if any state-changing commands were sent (not just period)
                                        state_changing_keys = {"output_voltage_set", "output_current_set", "ovp", "ocp",
                                                              "output_enable", "output_toggle", "preset_index"}
                                        if any(key in payload for key in state_changing_keys):
                                            # Schedule a delayed state query if one isn't already pending
                                            if identity not in self._pending_state_queries:
                                                self._pending_state_queries.add(identity)
                                                asyncio.create_task(self._delayed_state_query(identity, psu, 0.5))

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

                    finally:
                        # Always publish offline status before disconnecting (graceful shutdown)
                        self._logger.info("Publishing offline status before disconnect")
                        try:
                            await client.publish(availability_topic, payload="offline", qos=1, retain=True)
                        except:
                            pass

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

    async def _delayed_state_query(self, identity:str, psu, delay:float):
        """Queue a state query after a delay, allowing PSU to apply changes"""
        await asyncio.sleep(delay)
        psu.queue_state_get()
        # Clear pending flag so future commands can schedule new queries
        self._pending_state_queries.discard(identity)

    async def _mqtt_outbound(self, identity:str, state:dict):
        """Send MQTT state message on behalf of caller"""

        if self._mqtt_client:
            # Publish message
            try:
                topic = f"{self._mqtt_base_topic}/psu/{identity}/state"
                self._logger.debug("Msg leaving on topic: '%s', for identity: '%s' with payload: '%s'", topic, identity, repr(state))
                await self._mqtt_client.publish(topic, payload=json.dumps(state))

                # Update discovery with real firmware version if we haven't yet
                if (self._mqtt_discovery_enabled and
                    identity not in self._firmware_version_updated and
                    'firmware_version' in state and
                    identity in self._psus):

                    psu = self._psus[identity]
                    name = self._psu_identity_to_name.get(identity, "")
                    self._logger.info("Updating device info with firmware version %s for %s", state['firmware_version'], identity)
                    await self._publish_discovery_config(identity, psu.model, name, state['firmware_version'])
                    self._firmware_version_updated.add(identity)

            except aiomqtt.MqttError:
                # Ignore MQTT errors
                pass

    async def _publish_discovery_config(self, identity:str, model:int, name:str, firmware_version:str=None):
        """Publish Home Assistant MQTT Discovery configuration for a PSU"""

        if not self._mqtt_discovery_enabled or not self._mqtt_client:
            return

        self._logger.info("Publishing MQTT Discovery config for %s", identity)

        # Extract current rating from model number
        # Model format: VVCCR where VV=voltage, CC=current, R=revision
        # Example: 60301 = 60V, 30A, revision 1
        model_str = str(model)
        current_rating = int(model_str[2:4])

        # Set limits based on Riden PSU specifications
        # All RD60xx models: 60V max output, 62V max OVP
        # Current/OCP: nominal + 0.2A (e.g., 30A → 30.2A max)
        max_voltage = 60.0
        max_current = current_rating + 0.2
        max_ovp = max_voltage + 2.0

        # Device information shared by all entities
        device = {
            "identifiers": [identity],
            "name": name if name else f"Riden PSU {identity}",
            "model": f"RD{model}",
            "manufacturer": "Riden",
            "sw_version": firmware_version if firmware_version else "Unknown"
        }

        # State topic for sensors
        state_topic = f"{self._mqtt_base_topic}/psu/{identity}/state"
        command_topic = f"{self._mqtt_base_topic}/psu/{identity}/state/set"

        # Availability topic (bridge online/offline status)
        availability_topic = f"{self._mqtt_base_topic}/bridge/status"

        # Define all discovery configurations
        configs = []

        # Sensors (read-only)
        sensors = [
            # Device info
            {"name": "Model", "id": "model", "icon": "mdi:chip", "value_template": "{{ value_json.model }}"},
            {"name": "Serial Number", "id": "serial_no", "icon": "mdi:barcode", "value_template": "{{ value_json.serial_no }}"},
            {"name": "Firmware Version", "id": "firmware_version", "icon": "mdi:update", "value_template": "{{ value_json.firmware_version }}"},

            # Temperature
            {"name": "Temperature", "id": "temp_c", "unit": "°C", "device_class": "temperature", "state_class": "measurement", "value_template": "{{ value_json.temp_c }}"},
            {"name": "External Temperature", "id": "ext_temp_c", "unit": "°C", "device_class": "temperature", "state_class": "measurement", "value_template": "{{ value_json.ext_temp_c }}"},

            # Output measurements
            {"name": "Output Voltage", "id": "output_voltage_disp", "unit": "V", "device_class": "voltage", "state_class": "measurement", "icon": "mdi:lightning-bolt", "value_template": "{{ value_json.output_voltage_disp }}", "precision": 2},
            {"name": "Output Current", "id": "output_current_disp", "unit": "A", "device_class": "current", "state_class": "measurement", "icon": "mdi:current-dc", "value_template": "{{ value_json.output_current_disp }}", "precision": 2},
            {"name": "Output Power", "id": "output_power_disp", "unit": "W", "device_class": "power", "state_class": "measurement", "icon": "mdi:flash", "value_template": "{{ value_json.output_power_disp }}", "precision": 2},
            {"name": "Input Voltage", "id": "input_voltage", "unit": "V", "device_class": "voltage", "state_class": "measurement", "icon": "mdi:power-plug", "value_template": "{{ value_json.input_voltage }}", "precision": 2},

            # Status
            {"name": "Protection Status", "id": "protection_status", "icon": "mdi:shield-check", "value_template": "{{ value_json.protection_status }}"},
            {"name": "Output Mode", "id": "output_mode", "icon": "mdi:sine-wave", "value_template": "{{ value_json.output_mode | upper }}"},
            {"name": "Current Range", "id": "current_range", "unit": "A", "state_class": "measurement", "icon": "mdi:gauge", "value_template": "{% if value_json.current_range is defined %}{{ 6 if value_json.current_range == 0 else 12 }}{% else %}0{% endif %}"},

            # Battery
            {"name": "Battery Mode", "id": "battery_mode", "icon": "mdi:battery-charging", "value_template": "{{ value_json.battery_mode }}"},
            {"name": "Battery Voltage", "id": "battery_voltage", "unit": "V", "device_class": "voltage", "state_class": "measurement", "icon": "mdi:battery", "value_template": "{{ value_json.battery_voltage }}", "precision": 2},
            {"name": "Battery Amp Hours", "id": "battery_ah", "unit": "Ah", "state_class": "measurement", "icon": "mdi:battery-charging-100", "value_template": "{{ value_json.battery_ah }}", "precision": 3},
            {"name": "Battery Watt Hours", "id": "battery_wh", "unit": "Wh", "device_class": "energy", "state_class": "measurement", "icon": "mdi:lightning-bolt-circle", "value_template": "{{ value_json.battery_wh }}", "precision": 3},
        ]

        for sensor in sensors:
            config = {
                "name": sensor['name'],
                "unique_id": f"riden_{identity}_{sensor['id']}",
                "object_id": f"riden_{identity}_{sensor['id']}",
                "state_topic": state_topic,
                "value_template": sensor["value_template"],
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device
            }
            if "unit" in sensor:
                config["unit_of_measurement"] = sensor["unit"]
            if "device_class" in sensor:
                config["device_class"] = sensor["device_class"]
            if "state_class" in sensor:
                config["state_class"] = sensor["state_class"]
            if "icon" in sensor:
                config["icon"] = sensor["icon"]
            if "precision" in sensor:
                config["suggested_display_precision"] = sensor["precision"]

            topic = f"{self._mqtt_discovery_prefix}/sensor/riden_{identity}/{sensor['id']}/config"
            configs.append((topic, config))

        # Binary sensor for connection status
        connected_sensor = {
            "name": "Connected",
            "unique_id": f"riden_{identity}_connected",
            "object_id": f"riden_{identity}_connected",
            "state_topic": state_topic,
            "value_template": "{{ value_json.connected }}",
            "payload_on": True,
            "payload_off": False,
            "device_class": "connectivity",
            "icon": "mdi:connection",
            "availability_topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device
        }
        topic = f"{self._mqtt_discovery_prefix}/binary_sensor/riden_{identity}/connected/config"
        configs.append((topic, connected_sensor))

        # Switch for output enable control
        output_switch = {
            "name": "Output",
            "unique_id": f"riden_{identity}_output",
            "object_id": f"riden_{identity}_output",
            "state_topic": state_topic,
            "command_topic": command_topic,
            "value_template": "{{ value_json.output_enable }}",
            "payload_on": '{"output_enable": true}',
            "payload_off": '{"output_enable": false}',
            "state_on": True,
            "state_off": False,
            "icon": "mdi:power",
            "availability_topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": device
        }
        topic = f"{self._mqtt_discovery_prefix}/switch/riden_{identity}/output/config"
        configs.append((topic, output_switch))

        # Number controls (using dynamic limits based on PSU model)
        numbers = [
            {"name": "Set Voltage", "id": "set_voltage", "min": 0, "max": max_voltage, "step": 0.01, "unit": "V", "device_class": "voltage", "icon": "mdi:lightning-bolt", "value_template": "{{ value_json.output_voltage_set }}", "command_template": '{"output_voltage_set": {{ value }} }'},
            {"name": "Set Current", "id": "set_current", "min": 0, "max": max_current, "step": 0.01, "unit": "A", "device_class": "current", "icon": "mdi:current-dc", "value_template": "{{ value_json.output_current_set }}", "command_template": '{"output_current_set": {{ value }} }'},
            {"name": "OVP", "id": "set_ovp", "min": 0, "max": max_ovp, "step": 0.01, "unit": "V", "device_class": "voltage", "icon": "mdi:shield-alert", "value_template": "{{ value_json.ovp }}", "command_template": '{"ovp": {{ value }} }'},
            {"name": "OCP", "id": "set_ocp", "min": 0, "max": max_current, "step": 0.01, "unit": "A", "device_class": "current", "icon": "mdi:shield-alert", "value_template": "{{ value_json.ocp }}", "command_template": '{"ocp": {{ value }} }'},
            {"name": "Update Period", "id": "set_period", "min": 0, "max": 60, "step": 0.1, "unit": "s", "icon": "mdi:timer", "value_template": "{{ value_json.period }}", "command_template": '{"period": {{ value }} }'},
        ]

        for number in numbers:
            config = {
                "name": number['name'],
                "unique_id": f"riden_{identity}_{number['id']}",
                "object_id": f"riden_{identity}_{number['id']}",
                "state_topic": state_topic,
                "command_topic": command_topic,
                "value_template": number["value_template"],
                "command_template": number["command_template"],
                "min": number["min"],
                "max": number["max"],
                "step": number["step"],
                "mode": "box",
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device
            }
            if "unit" in number:
                config["unit_of_measurement"] = number["unit"]
            if "device_class" in number:
                config["device_class"] = number["device_class"]
            if "icon" in number:
                config["icon"] = number["icon"]

            topic = f"{self._mqtt_discovery_prefix}/number/riden_{identity}/{number['id']}/config"
            configs.append((topic, config))

        # Buttons
        buttons = [
            {"name": "Request State", "id": "request_state", "icon": "mdi:refresh", "payload": '{"query": true}', "command_topic": f"{self._mqtt_base_topic}/psu/{identity}/state/get"},
        ]

        for button in buttons:
            config = {
                "name": button['name'],
                "unique_id": f"riden_{identity}_{button['id']}",
                "object_id": f"riden_{identity}_{button['id']}",
                "command_topic": button.get("command_topic", command_topic),
                "payload_press": button["payload"],
                "icon": button["icon"],
                "availability_topic": availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device
            }

            topic = f"{self._mqtt_discovery_prefix}/button/riden_{identity}/{button['id']}/config"
            configs.append((topic, config))

        # Publish all configurations
        try:
            for topic, config in configs:
                await self._mqtt_client.publish(topic, payload=json.dumps(config), retain=True)
            self._logger.info("Published %d MQTT Discovery configs for %s", len(configs), identity)
        except aiomqtt.MqttError as e:
            self._logger.error("Failed to publish MQTT Discovery configs: %s", e)

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

                # Set default update period if not already configured
                if state.update_period is None:
                    state.update_period = self._default_update_period

                # Create new bridge instance
                psu_bridge = Bridge(host, port, identity, model, serial_no, psu, state, self._mqtt_outbound, self._set_clock_on_connection)

                # Add bridge instance to map
                self._psus[identity] = psu_bridge

                # Publish MQTT Discovery configuration if enabled
                await self._publish_discovery_config(identity, model, name)

                # Query initial state so entities have data immediately
                psu_bridge.queue_state_get()

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
