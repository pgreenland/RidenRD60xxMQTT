from typing import Callable, Tuple
import asyncio
import logging
import time

import pymodbus

from rd60xx import RD60xx, RD60xxStateSet
from psu_state import PSUState

class Bridge:
    """Bridge implementation for single PSU"""

    def __init__(self, host:str, port:int, identity:str, model:int, serial_no:int, psu:RD60xx, persistent_state:PSUState, publish_callback:Callable, set_clock_on_connection:bool=False) -> None:
        """Constructor"""

        # Store arguments
        self._host = host
        self._port = port
        self._identity = identity
        self._model = model
        self._serial_no = serial_no
        self._psu = psu
        self._persistent_state = persistent_state
        self._publish_callback = publish_callback
        self._set_clock_on_connection = set_clock_on_connection

        # Construct logger
        self._logger = logging.getLogger("Bridge")

        # Construct inbound request queue
        self._inbound_queue = asyncio.Queue(maxsize=64)

        # Reset last query time
        self._last_query_time = 0

        # Start psu task
        self._psu_task = asyncio.create_task(self._psu_task_func())

    @property
    def host_port(self):
        """Retrieve host and port"""

        return f"{self._host}:{self._port}"

    @property
    def identity(self):
        """Retrieve PSU identity"""

        return self._identity

    @property
    def model(self):
        """Retrieve PSU model"""

        return self._model

    @property
    def serial_no(self):
        """Retrieve PSU serial number"""

        return self._serial_no

    @property
    def client(self):
        """Retrieve pymodbus client for PSU"""

        return self._psu

    def queue_state_get(self):
        """Queue a state get request for PSU"""

        # Push get request
        try:
            self._inbound_queue.put_nowait((False, None))
        except asyncio.QueueFull:
            pass

    def queue_state_set(self, request:dict):
        """Queue a state set request for PSU"""

        # Push set request
        try:
            self._inbound_queue.put_nowait((True, request))
        except asyncio.QueueFull:
            pass

    def cancel(self):
        """Cancel worker task for PSU"""

        self._psu_task.cancel()

    async def _psu_task_func(self):
        """PSU worker task, periodically queries unit (if enabled, publishing state, while updating unit with received state"""

        try:
            if self._set_clock_on_connection:
                # Set PSU clock before entering main loop
                self._logger.debug("Set clock for %s", self._identity)
                await self._set_clock()

            # Main loop
            while True:
                # Process any requests in queue
                while not self._inbound_queue.empty():
                    # Dequeue item
                    entry = self._inbound_queue.get_nowait()

                    # Process message
                    await self._process_queue_entry(entry)

                # Block on queue until next query time reached
                try:
                    # Calculate timeout, assume none (blocking read), or >= 0 if querying enabled
                    timeout = None
                    if self._persistent_state.update_period > 0:
                        # Calculate timeout before next query, limiting to zero if already late
                        timeout = max(self._persistent_state.update_period - (time.monotonic() - self._last_query_time), 0)

                    # Dequeue item, waiting between some and infinite time
                    entry = await asyncio.wait_for(self._inbound_queue.get(), timeout=timeout)

                    # Process message
                    await self._process_queue_entry(entry)

                except asyncio.TimeoutError:
                    # No message retrieved within timeout
                    pass

                # Check for periodic query
                if self._persistent_state.update_period > 0:
                    # Sample current time
                    curr_time = time.monotonic()

                    # Calculate elapsed time since last query
                    elapsed_time = curr_time - self._last_query_time

                    # Has query period been reached
                    if elapsed_time > self._persistent_state.update_period:
                        # Query psu
                        await self._get_state()

        except pymodbus.ModbusException:
            # Modbus connection gone boom, close connection
            self._logger.exception("Modbus exception in psu_task")

            # Close connection
            try:
                self.close()
            except:
                pass

        except asyncio.CancelledError:
            # Task canclled
            pass

        except:
            # General exception
            self._logger.exception("Exception in psu_task")

    async def _process_queue_entry(self, entry:Tuple[bool, dict]):
        """Handle single entry from queue"""

        # Split request
        set, req = entry

        # Process message
        if set:
            # Set request, provide new settings to PSU
            self._logger.debug("Set state for %s (%s)", self._identity, repr(req))
            await self._set_state(req)

        else:
            # Get request, query unit state
            self._logger.debug("Get state for %s", self._identity)
            await self._get_state()

    async def _set_clock(self):
        """Set date / time on unit"""

        # Retrieve local time
        t = time.localtime()

        # Pass to unit
        await self._psu.set_clock(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)

    async def _set_state(self, msg:dict):
        """Handle new state arriving from MQTT"""

        # Extract fields
        try:
            preset_index = msg.get("preset_index")
            if preset_index is not None:
                preset_index = int(preset_index)
            output_voltage_set = msg.get("output_voltage_set")
            if output_voltage_set is not None:
                output_voltage_set = float(output_voltage_set)
            output_current_set = msg.get("output_current_set")
            if output_current_set is not None:
                output_current_set = float(output_current_set)
            ovp = msg.get("ovp")
            if ovp is not None:
                ovp = float(ovp)
            ocp = msg.get("ocp")
            if ocp is not None:
                ocp = float(ocp)
            output_enable = msg.get("output_enable")
            if output_enable is not None:
                output_enable = bool(output_enable)
            output_toggle = msg.get("output_toggle")
            if output_toggle is not None:
                output_toggle = bool(output_toggle)
        except:
            # Ignore any decode failures and bail
            self._logger.warning("Bad set data for identity %s", self._identity)
            return

        # Construct state
        state = RD60xxStateSet(
            preset_index,
            output_voltage_set,
            output_current_set,
            ovp,
            ocp,
            output_enable,
            output_toggle
        )

        # Write state
        await self._psu.set_state(state)

    async def _get_state(self):
        """Query unit and pubish current data via MQTT"""

        # Query unit
        state = await self._psu.get_state()

        # Was unit was queried successfully?
        if state is not None:
            # Yes, prepare message
            msg = {}

            # Add fields
            msg["connected"] = True
            msg["period"] = self._persistent_state.update_period
            msg["model"] = state.model
            msg["serial_no"] = state.serial_no
            msg["firmware_version"] = state.firmware_version
            msg["temp_c"] = state.temp_c
            msg["temp_f"] = state.temp_f
            msg["current_range"] = state.current_range
            msg["output_voltage_set"] = state.output_voltage_set
            msg["output_current_set"] = state.output_current_set
            msg["ovp"] = state.ovp
            msg["ocp"] = state.ocp
            msg["output_voltage_disp"] = state.output_voltage_disp
            msg["output_current_disp"] = state.output_current_disp
            msg["output_power_disp"] = state.output_power_disp
            msg["input_voltage"] = state.input_voltage
            protection_status = state.protection_status
            if protection_status == 0:
                protection_status = "normal"
            elif protection_status == 1:
                protection_status = "ovp"
            elif protection_status == 2:
                protection_status = "ocp"
            else:
                protection_status = "unknown"
            msg["protection_status"] = protection_status
            output_mode = state.output_mode
            if output_mode == 0:
                 output_mode = "cv"
            elif output_mode == 1:
                 output_mode = "cc"
            else:
                 output_mode = "unknown"
            msg["output_mode"] = output_mode
            msg["output_enable"] = state.output_enable
            msg["battery_mode"] = state.battery_mode
            msg["battery_voltage"] = state.battery_voltage
            msg["ext_temp_c"] = state.ext_temp_c
            msg["ext_temp_f"] = state.ext_temp_f
            msg["batt_ah"] = state.batt_ah
            msg["batt_wh"] = state.batt_wh
            presets = []
            for x in state.presets:
                 # Split up preset
                 volt, curr, ovp, ocp = x

                # Add dict
                 presets.append({"v":volt, "c":curr, "ovp":ovp, "ocp":ocp})
            msg["presets"] = presets

            # Publish state message
            await self._publish_callback(self.identity, msg)

            # Update last query time
            self._last_query_time = time.monotonic()
