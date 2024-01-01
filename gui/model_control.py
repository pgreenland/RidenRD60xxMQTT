import asyncio
import json
from typing import Optional
import aiomqtt

from view_intfc import RidenPSUViewIntfc, RidenPSUListEntry

class RidenPSUModelControl:
    """Model / controller-esq class, managing MQTT connection and interaction between GUI and broker"""

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
                 mqtt_reconnect_delay_secs:float=5,
                 mqtt_probe_delay_secs:float=1) -> None:
        """Start and maintain MQTT connection"""

        # Store arguments
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
        self._mqtt_reconnect_delay_secs = mqtt_reconnect_delay_secs
        self._mqtt_probe_delay_secs = mqtt_probe_delay_secs

        # Reset MQTT tasks
        self._mqtt_task_in = None
        self._mqtt_task_out = None

        # Reset MQTT client
        self._mqtt_client = None

        # Reset selected psu
        self._psu_identity = None

        # Reset topic wildcard
        self._wildcard_state = None

        # Reset recevied message count
        self._count_received = 0

    def set_view(self, view:RidenPSUViewIntfc):
        """Update view for model / controller"""

        self._view = view

    def run(self) -> None:
        """Start and maintain MQTT connection"""

        # Retreive event loop
        loop = asyncio.get_event_loop()

        # Create task to manage MQTT connection and process inbound messages
        self._mqtt_task = None
        loop.call_soon_threadsafe(self._start_mqtt_task)

    def stop(self) -> None:
        """Request MQTT client stop"""

        # Retreive event loop
        loop = asyncio.get_event_loop()

        # Cancel MQTT task
        loop.call_soon_threadsafe(self._stop_mqtt_task)

    def _start_mqtt_task(self):
        """Start MQTT task"""

        # Retreive event loop
        loop = asyncio.get_event_loop()

        # Create task
        self._mqtt_task_in = loop.create_task(self._mqtt_inbound())
        self._mqtt_task_out = loop.create_task(self._mqtt_outbound())

    def _stop_mqtt_task(self) -> None:
        """Request MQTT client stop"""

        # Cancel MQTT task
        if self._mqtt_task_in is not None:
            self._mqtt_task_in.cancel()
        if self._mqtt_task_out is not None:
            self._mqtt_task_out.cancel()

    async def _mqtt_inbound(self):
        """Connect and reconnect to MQTT broker as required, subscribing to and reading messages"""

        while True:
            try:
                if self._hostname is None or self._port is None:
                    # Need a config to get any further
                    break

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
                    # Make client available to psu connection handler
                    self._mqtt_client = client

                    # Subscribe to PSU topics
                    await client.subscribe(f"{self._mqtt_base_topic}/psu/list")

                    # Prepare wildcards
                    wildcard_psus_list = f"{self._mqtt_base_topic}/psu/list"

                    # Publish request for PSU list
                    await client.publish(topic=f"{self._mqtt_base_topic}/psu/list/get", payload=json.dumps({}), qos=1)

                    # Subscribe to target PSU and prepare wildcard
                    await self._subscribe_to_psu()

                    # Retrive messages
                    async with client.messages() as messages:
                        # Process messages
                        async for message in messages:
                            # Attempt to de-serialize message
                            try:
                                payload = json.loads(message.payload)
                            except:
                                continue

                            # Act on topics
                            if self._wildcard_state is not None and message.topic.matches(self._wildcard_state):
                                # State report, update GUI
                                if self._view is not None:
                                    self._view.set_connected(payload.get("connected", False))
                                    self._view.set_update_state(payload.get("period", 0) > 0)
                                    if "current_range" in payload:
                                        self._view.set_current_range(payload["current_range"])
                                    if "input_voltage" in payload:
                                        self._view.set_input_voltage(payload["input_voltage"])
                                    if "output_voltage_set" in payload:
                                        self._view.set_output_voltage_set(payload["output_voltage_set"])
                                    if "output_current_set" in payload:
                                        self._view.set_output_current_set(payload["output_current_set"])
                                    if "ovp" in payload:
                                        self._view.set_ovp(payload["ovp"])
                                    if "ocp" in payload:
                                        self._view.set_ocp(payload["ocp"])
                                    if "output_voltage_disp" in payload:
                                        self._view.set_output_voltage_disp(payload["output_voltage_disp"])
                                    if "output_current_disp" in payload:
                                        self._view.set_output_current_disp(payload["output_current_disp"])
                                    if "output_power_disp" in payload:
                                        self._view.set_output_power_disp(payload["output_power_disp"])
                                    if "output_mode" in payload:
                                        self._view.set_cc_cv(payload["output_mode"] == "cc")
                                    if "protection_status" in payload:
                                        self._view.set_ovp_ocp(payload["protection_status"])
                                    if "battery_mode" in payload:
                                        self._view.set_batt_state(payload["battery_mode"])
                                    if "ext_temp_c" in payload:
                                        self._view.set_temp(payload["ext_temp_c"])
                                    if "batt_ah" in payload:
                                        self._view.set_batt_ah(payload["batt_ah"])
                                    if "batt_wh" in payload:
                                        self._view.set_batt_wh(payload["batt_wh"])
                                    if "output_enable" in payload:
                                        self._view.set_output_enabled(payload["output_enable"])

                                # Inc counter
                                self._count_received += 1

                            elif message.topic.matches(wildcard_psus_list):
                                # PSU list, update GUI
                                if self._view is not None:
                                    # Prepare list of PSUS
                                    psus = []
                                    for x in payload:
                                        if "identity" in x and "name" in x and "model" in x and "serial_no" in x:
                                            psus.append(RidenPSUListEntry(x["identity"], x["name"], x["model"], x["serial_no"]))

                                    # Inform GUI
                                    self._view.set_psus(psus)

            except aiomqtt.MqttError:
                # MQTT connection failed, reset client
                self._mqtt_client = None

                # Report unit disconnected until broker reconnected
                if self._view is not None:
                    self._view.set_connected(False)

                # Wait a while before reconnecting
                await asyncio.sleep(self._mqtt_reconnect_delay_secs)

            except asyncio.CancelledError:
                # Task cancelled, reset client
                self._mqtt_client = None
                break

    async def _mqtt_outbound(self):
        """Probe MQTT for connection status if PSU data isn't returned for a period of time"""

        # Reset number of probes
        count_sent = 0

        try:
            while True:
                # Wait a while
                await asyncio.sleep(self._mqtt_probe_delay_secs)

                # Check message received
                if self._count_received == 0:
                    # No messages, received probe for PSU status
                    if self._mqtt_client is not None and self._psu_identity is not None:
                        try:
                            await self._mqtt_client.publish(f"{self._mqtt_base_topic}/psu/{self._psu_identity}/state/get", payload=json.dumps({"query" : False}))
                        except aiomqtt.MqttError:
                            pass

                    # Inc counter
                    count_sent += 1

                    # Clear connected status after x replies
                    if count_sent >= 3 and self._view is not None:
                        self._view.set_connected(False)

                else:
                    # Reset counter
                    count_sent = 0

                # Reset counter
                self._count_received = 0

        except asyncio.CancelledError:
            # Task cancelled
            pass

    def set_psu(self, identity:str) -> None:
        """Set PSU to monitor / control"""

        asyncio.run_coroutine_threadsafe(self._subscribe_to_psu(identity), asyncio.get_event_loop())

    async def _subscribe_to_psu(self, new_identity:Optional[str]=None):
        """Subscribe (or resubscribe) to (possibly different) PSU"""

        if new_identity is not None and self._psu_identity is not None:
            # New identity being set, unsubscribe from old one
            if self._mqtt_client is not None:
                try:
                    await self._mqtt_client.unsubscribe(f"{self._mqtt_base_topic}/psu/{self._psu_identity}/state")
                except aiomqtt.MqttError:
                    pass

        if new_identity is not None:
            # Update PSU
            self._psu_identity = new_identity

        if self._psu_identity is not None:
            # Subscribe
            await self._mqtt_client.subscribe(f"{self._mqtt_base_topic}/psu/{self._psu_identity}/state")

            # Prepare topic wildcard
            self._wildcard_state = f"{self._mqtt_base_topic}/psu/{self._psu_identity}/state"

        # Request a single query from the PSU
        await self._mqtt_publish_state_get({"query" : True})

    # Interface implementation, passing requests to asyncio thread for processing
    def set_update(self, enabled:bool) -> None:
        """Set update period (auto-update enabled / disabled)"""
        asyncio.run_coroutine_threadsafe(self._set_update(enabled), asyncio.get_event_loop())

    def set_voltage(self, value:float) -> None:
        """Set new voltage"""
        asyncio.run_coroutine_threadsafe(self._set_voltage(value), asyncio.get_event_loop())

    def set_current(self, value:float) -> None:
        """Set new current"""
        asyncio.run_coroutine_threadsafe(self._set_current(value), asyncio.get_event_loop())

    def set_ovp(self, value:float) -> None:
        """Set new over-voltage protection limit"""
        asyncio.run_coroutine_threadsafe(self._set_ovp(value), asyncio.get_event_loop())

    def set_ocp(self, value:float) -> None:
        """Set new over-current protection limit"""
        asyncio.run_coroutine_threadsafe(self._set_ocp(value), asyncio.get_event_loop())

    def set_preset(self, index:int) -> None:
        """Set new preset number"""
        asyncio.run_coroutine_threadsafe(self._set_preset(index), asyncio.get_event_loop())

    def toggle_output_enable(self) -> None:
        """Toggle output state"""
        asyncio.run_coroutine_threadsafe(self._toggle_output_enable(), asyncio.get_event_loop())

    # Asyncio helper functions
    async def _set_update(self, enabled:bool) -> None:
        """Set update period (auto-update enabled / disabled) - helper"""

        await self._mqtt_publish_state_set({"period" : 0.25 if enabled else 0.0})

    async def _set_voltage(self, value:float) -> None:
        """Set new voltage - helper"""

        await self._mqtt_publish_state_set({"output_voltage_set" : value})

    async def _set_current(self, value:float) -> None:
        """Set new current - helper"""

        await self._mqtt_publish_state_set({"output_current_set" : value})

    async def _set_ovp(self, value:float) -> None:
        """Set new over-voltage protection limit - helper"""

        await self._mqtt_publish_state_set({"ovp" : value})

    async def _set_ocp(self, value:float) -> None:
        """Set new over-current protection limit - helper"""

        await self._mqtt_publish_state_set({"ocp" : value})

    async def _set_preset(self, index:int) -> None:
        """Set new preset number - helper"""

        await self._mqtt_publish_state_set({"preset_index" : index})

    async def _toggle_output_enable(self) -> None:
        """Toggle output state - helper"""

        await self._mqtt_publish_state_set({"output_toggle" : True})

    async def _mqtt_publish_state_get(self, state:dict):
        """Publish state set request on current PSU topic"""

        if self._mqtt_client is not None and self._psu_identity is not None:
            try:
                await self._mqtt_client.publish(f"{self._mqtt_base_topic}/psu/{self._psu_identity}/state/get", payload=json.dumps(state))
            except aiomqtt.MqttError:
                pass

    async def _mqtt_publish_state_set(self, state:dict):
        """Publish state set request on current PSU topic"""

        if self._mqtt_client is not None and self._psu_identity is not None:
            try:
                await self._mqtt_client.publish(f"{self._mqtt_base_topic}/psu/{self._psu_identity}/state/set", payload=json.dumps(state))
            except aiomqtt.MqttError:
                pass
