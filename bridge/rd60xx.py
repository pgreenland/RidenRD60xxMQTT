from typing import Any, Optional
import enum
import time

from pymodbus.framer.base import FramerType
from pymodbus.exceptions import ModbusException

from async_modbus_reverse_tcp_client import AsyncModbusReverseTcpClient

class RD60xxStateGet:
    """Represents state returned from PSU"""

    def __init__(self,
                 model:int,
                 serial_no:int,
                 firmware_version:str,
                 temp_c:float,
                 temp_f:float,
                 current_range:int,
                 output_voltage_set:float,
                 output_current_set:float,
                 ovp:float,
                 ocp:float,
                 output_voltage_disp:float,
                 output_current_disp:float,
                 output_power_disp:float,
                 input_voltage:float,
                 protection_status:int, # 0 = None, 1 = OVP, 2 = OCP
                 output_mode:int, # 0 = CV, 1 = CC
                 output_enable:bool,
                 battery_mode:bool,
                 battery_voltage:float,
                 ext_temp_c:float,
                 ext_temp_f:float,
                 batt_ah:float,
                 batt_wh:float,
                 presets:list[tuple[float, float, float, float]] # voltage, current, ovp, ocp
                 ) -> None:
        """Store provided arguments"""

        self._model = model
        self._serial_no = serial_no
        self._firmware_version = firmware_version
        self._temp_c = temp_c
        self._temp_f = temp_f
        self._current_range = current_range
        self._output_voltage_set = output_voltage_set
        self._output_current_set = output_current_set
        self._ovp = ovp
        self._ocp = ocp
        self._output_voltage_disp = output_voltage_disp
        self._output_current_disp = output_current_disp
        self._output_power_disp = output_power_disp
        self._input_voltage = input_voltage
        self._protection_status = protection_status
        self._output_mode = output_mode
        self._output_enable = output_enable
        self._battery_mode = battery_mode
        self._battery_voltage = battery_voltage
        self._ext_temp_c = ext_temp_c
        self._ext_temp_f = ext_temp_f
        self._batt_ah = batt_ah
        self._batt_wh = batt_wh
        self._presets = presets

    @property
    def model(self) -> int:
        return self._model

    @property
    def serial_no(self) -> int:
        return self._serial_no

    @property
    def firmware_version(self) -> str:
        return self._firmware_version

    @property
    def temp_c(self) -> float:
        return self._temp_c

    @property
    def temp_f(self) -> float:
        return self._temp_f

    @property
    def current_range(self) -> int:
        return self._current_range

    @property
    def output_voltage_set(self) -> float:
        return self._output_voltage_set

    @property
    def output_current_set(self) -> float:
        return self._output_current_set

    @property
    def ovp(self) -> float:
        return self._ovp

    @property
    def ocp(self) -> float:
        return self._ocp

    @property
    def output_voltage_disp(self) -> float:
        return self._output_voltage_disp

    @property
    def output_current_disp(self) -> float:
        return self._output_current_disp

    @property
    def output_power_disp(self) -> float:
        return self._output_power_disp

    @property
    def input_voltage(self) -> float:
        return self._input_voltage

    @property
    def protection_status(self) -> int:
        return self._protection_status

    @property
    def output_mode(self) -> int:
        return self._output_mode

    @property
    def output_enable(self) -> bool:
        return self._output_enable

    @property
    def battery_mode(self) -> bool:
        return self._battery_mode

    @property
    def battery_voltage(self) -> float:
        return self._battery_voltage

    @property
    def ext_temp_c(self) -> float:
        return self._ext_temp_c

    @property
    def ext_temp_f(self) -> float:
        return self._ext_temp_f

    @property
    def batt_ah(self) -> float:
        return self._batt_ah

    @property
    def batt_wh(self) -> float:
        return self._batt_wh

    @property
    def presets(self) -> list[tuple[float, float, float, float]]:
        return self._presets

class RD60xxStateSet:
    """Represents state provided to PSU"""

    def __init__(self,
                 preset_index:Optional[int]=None,
                 output_voltage_set:Optional[float] = None,
                 output_current_set:Optional[float] = None,
                 ovp:Optional[float] = None,
                 ocp:Optional[float] = None,
                 output_enable:Optional[bool]=None,
                 output_toggle:Optional[bool]=None
                 ) -> None:
        """Store provided arguments"""

        self._preset_index = preset_index
        if self._preset_index is not None:
            self._preset_index = int(self._preset_index)

        self._output_voltage_set = output_voltage_set
        if self._output_voltage_set is not None:
            self._output_voltage_set = float(self._output_voltage_set)

        self._output_current_set = output_current_set
        if self._output_current_set is not None:
            self._output_current_set = float(self._output_current_set)

        self._ovp = ovp
        if self._ovp is not None:
            self._ovp = float(self._ovp)

        self._ocp = ocp
        if self._ocp is not None:
            self._ocp = float(self._ocp)

        self._output_enable = output_enable
        if self._output_enable is not None:
            self._output_enable = bool(self._output_enable)

        self._output_toggle = output_toggle
        if self._output_toggle is not None:
            self._output_toggle = bool(self._output_toggle)

    @property
    def preset_index(self) -> int:
        return self._preset_index

    @property
    def output_voltage_set(self) -> float:
        return self._output_voltage_set

    @property
    def output_current_set(self) -> float:
        return self._output_current_set

    @property
    def ovp(self) -> float:
        return self._ovp

    @property
    def ocp(self) -> float:
        return self._ocp

    @property
    def output_enable(self) -> bool:
        return self._output_enable

    @property
    def output_toggle(self) -> bool:
        return self._output_toggle

class RD60xx(AsyncModbusReverseTcpClient):
    """Wrapper around pymodbus client, implementing PSU reads and writes"""

    # RD60xx registers
    # From: https://github.com/Baldanos/rd6006/blob/master/registers.md
    class RD60xxRegisters(enum.Enum):
        MODEL = 0
        SERIAL_HI = 1
        SERIAL_LO = 2
        FIRMWARE = 3
        TEMP_DEG_C_SIGN = 4 # 0 = +ve, 1 = -ve
        TEMP_DEG_C_VALUE = 5
        TEMP_DEG_F_SIGN = 6 # 0 = +ve, 1 = -ve
        TEMP_DEG_F_VALUE = 7
        OUTPUT_VOLTAGE_SET = 8
        OUTPUT_CURRENT_SET = 9
        OUTPUT_VOLTAGE_DISP = 10
        OUTPUT_CURRENT_DISP = 11
        OUTPUT_POWER_DISP_HI = 12
        OUTPUT_POWER_DISP_LO = 13
        INPUT_VOLTAGE = 14
        KEYPAD_LOCK = 15
        PROTECTION_STATUS = 16 # 0 = none, 1 = OVP, 2 = OCP
        OUTPUT_MODE = 17 # 0 = CV, 1 = CC
        OUTPUT_ENABLE = 18
        PRESET = 19
        CURRENT_RANGE = 20 # RD6012P and possibly others (0 = 6A, 1=12A)
        # Unused
        BATTERY_MODE = 32
        BATTERY_VOLTAGE = 33
        EXT_TEMP_DEG_C_SIGN = 34 # 0 = +ve, 1 = -ve
        EXT_TEMP_DEG_C_VALUE = 35
        EXT_TEMP_DEG_F_SIGN = 36 # 0 = +ve, 1 = -ve
        EXT_TEMP_DEG_F_VALUE = 37
        BATT_AH_HI = 38
        BATT_AH_LO = 39
        BATT_WH_HI = 40
        BATT_WH_LO = 41
        # Unused
        YEAR = 48
        MONTH = 49
        DAY = 50
        HOUR = 51
        MINUTE = 52
        SECOND = 53
        # Unused / unmapped (some are calibration registers we're staying away from)
        M0_V = 80
        M0_C = 81
        M0_OVP = 82
        M0_OCP = 83
        M1_V = 84
        M1_C = 85
        M1_OVP = 86
        M1_OCP = 87
        # M2 -> M8 as above
        M9_V = 116
        M9_C = 117
        M9_OVP = 118
        M9_OCP = 119

    # PSU address
    PSU_ADDR = 1

    # Field scalings
    FIRMWARE_SCALE = 100.0
    INPUT_VOLTAGE_SCALE = 100.0
    DEFAULT_VOLTAGE_SCALE = 100.0
    MODEL_VOLTAGE_SCALINGS = {
        60125 : 1000.0,
    }
    DEFAULT_CURRENT_SCALE = (100.0, False) # (scale, uses current range)
    MODEL_CURRENT_SCALINGS = {
        # model : (scale, uses current range)
        6006 : (1000.0, False),
        60125 : (1000.0, True),
    }
    DEFAULT_POWER_SCALE = 100.0
    MODEL_POWER_SCALINGS = {
        60125 : 1000.0,
    }

    BATT_SCALE = 1000.0

    # To save querying PSU too much, only refresh presets periodically
    PRESET_READ_INTERVAL = 5 # sec

    def __init__(self, client_connected_cb, client_disconnected_cb, **kwargs: Any) -> None:
        """Constructor"""

        # Init parent
        AsyncModbusReverseTcpClient.__init__(self, client_connected_cb, client_disconnected_cb, framer=FramerType.RTU, **kwargs)

        # Reset presets
        self._presets = None
        self._presets_last_read = 0

    async def set_clock(self, year:int, month:int, day:int, hour:int, minute:int, second:int):
        """Set time/date"""

        # Pack registers into list
        clock_registers = [
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute),
            int(second)
        ]

        # Write clock registers
        await self.write_registers(device_id=self.PSU_ADDR, address=self.RD60xxRegisters.YEAR.value, values=clock_registers)

    async def get_state(self) -> Optional[RD60xxStateGet]:
        """Read and return current PSU status summary"""

        # Reset state
        state = None

        try:
            # Request reading block of registers from PSU (note this includes some unmapped registers)
            read_count = self.RD60xxRegisters.BATT_WH_LO.value - self.RD60xxRegisters.MODEL.value + 1
            response = await self.read_holding_registers(device_id=self.PSU_ADDR,
                                                         address=self.RD60xxRegisters.MODEL.value,
                                                         count=read_count)
            regs_a = response.registers
            if len(regs_a) != read_count:
                raise Exception("Wrong number of registered returned")

            # Get register value (offsetting to start of read)
            geta = lambda x : regs_a[x.value - self.RD60xxRegisters.MODEL.value]

            # Get a 32-bit register
            get32a = lambda hi, lo : (geta(hi) << 16) | geta(lo)

            # Helper to convert temperatures
            temp = lambda sign, val : (-1 if geta(sign) == 1 else 1) * geta(val)

            # Lookup voltage and current scaling, with and without hardware revision
            model_inc_hw_rev = geta(self.RD60xxRegisters.MODEL)
            model_exc_hw_rev = model_inc_hw_rev // 10
            if model_inc_hw_rev in self.MODEL_VOLTAGE_SCALINGS:
                voltage_scale = self.MODEL_VOLTAGE_SCALINGS[model_inc_hw_rev]
            else:
                voltage_scale = self.MODEL_VOLTAGE_SCALINGS.get(model_exc_hw_rev, self.DEFAULT_VOLTAGE_SCALE)
            if model_inc_hw_rev in self.MODEL_CURRENT_SCALINGS:
                current_scale = self.MODEL_CURRENT_SCALINGS[model_inc_hw_rev]
            else:
                current_scale = self.MODEL_CURRENT_SCALINGS.get(model_exc_hw_rev, self.DEFAULT_CURRENT_SCALE)
            if model_inc_hw_rev in self.MODEL_POWER_SCALINGS:
                power_scale = self.MODEL_POWER_SCALINGS[model_inc_hw_rev]
            else:
                power_scale = self.MODEL_POWER_SCALINGS.get(model_exc_hw_rev, self.DEFAULT_POWER_SCALE)

            # Split current scale
            current_scale, use_current_range = current_scale

            # Snapshot current scale before applying range
            current_scale_without_range = current_scale

            # Retrieve current range
            if use_current_range:
                current_range = geta(self.RD60xxRegisters.CURRENT_RANGE)
                if current_range == 0:
                    current_scale *= 10

            # Request reading block of registers from PSU (M0 for OVP and OCP)
            response = await self.read_holding_registers(device_id=self.PSU_ADDR,
                                                         address=self.RD60xxRegisters.M0_OVP.value,
                                                         count=2)
            regs_b = response.registers
            if len(regs_b) != 2:
                raise Exception("Wrong number of registered returned")

            # Get register value (offsetting to start of read)
            getb = lambda x : regs_b[x.value - self.RD60xxRegisters.M0_OVP.value]

            # Refresh presets periodically
            await self._read_presets(voltage_scale, current_scale)

            # Init state
            state = RD60xxStateGet(geta(self.RD60xxRegisters.MODEL),
                                   get32a(self.RD60xxRegisters.SERIAL_HI, self.RD60xxRegisters.SERIAL_LO),
                                   str(geta(self.RD60xxRegisters.FIRMWARE) / self.FIRMWARE_SCALE),
                                   temp(self.RD60xxRegisters.TEMP_DEG_C_SIGN, self.RD60xxRegisters.TEMP_DEG_C_VALUE),
                                   temp(self.RD60xxRegisters.TEMP_DEG_F_SIGN, self.RD60xxRegisters.TEMP_DEG_F_VALUE),
                                   geta(self.RD60xxRegisters.CURRENT_RANGE),
                                   geta(self.RD60xxRegisters.OUTPUT_VOLTAGE_SET) / voltage_scale,
                                   geta(self.RD60xxRegisters.OUTPUT_CURRENT_SET) / current_scale,
                                   getb(self.RD60xxRegisters.M0_OVP) / voltage_scale,
                                   getb(self.RD60xxRegisters.M0_OCP) / current_scale_without_range,
                                   geta(self.RD60xxRegisters.OUTPUT_VOLTAGE_DISP) / voltage_scale,
                                   geta(self.RD60xxRegisters.OUTPUT_CURRENT_DISP) / current_scale,
                                   get32a(self.RD60xxRegisters.OUTPUT_POWER_DISP_HI, self.RD60xxRegisters.OUTPUT_POWER_DISP_LO) / power_scale,
                                   geta(self.RD60xxRegisters.INPUT_VOLTAGE) / self.INPUT_VOLTAGE_SCALE,
                                   geta(self.RD60xxRegisters.PROTECTION_STATUS),
                                   geta(self.RD60xxRegisters.OUTPUT_MODE),
                                   geta(self.RD60xxRegisters.OUTPUT_ENABLE) != 0,
                                   geta(self.RD60xxRegisters.BATTERY_MODE) != 0,
                                   geta(self.RD60xxRegisters.BATTERY_VOLTAGE) / voltage_scale,
                                   temp(self.RD60xxRegisters.EXT_TEMP_DEG_C_SIGN, self.RD60xxRegisters.EXT_TEMP_DEG_C_VALUE),
                                   temp(self.RD60xxRegisters.EXT_TEMP_DEG_F_SIGN, self.RD60xxRegisters.EXT_TEMP_DEG_F_VALUE),
                                   get32a(self.RD60xxRegisters.BATT_AH_HI, self.RD60xxRegisters.BATT_AH_LO) / self.BATT_SCALE,
                                   get32a(self.RD60xxRegisters.BATT_WH_HI, self.RD60xxRegisters.BATT_WH_LO) / self.BATT_SCALE,
                                   self._presets
                                  )

        except (ModbusException, Exception):
            # Expect to return empty state
            pass

        return state

    async def _read_presets(self, voltage_scale:float, current_scale:float):
        """Refresh presets periodically"""

        # Retrieve time
        curr_time = time.monotonic()

        # Calculate elapsed time since last refresh
        elapsed_time = curr_time - self._presets_last_read

        # Check time (forcing refresh if we dont have a cached list)
        if elapsed_time > self.PRESET_READ_INTERVAL or self._presets is None:
            # Request reading block of registers from PSU
            read_count = self.RD60xxRegisters.M9_OCP.value - self.RD60xxRegisters.M1_V.value + 1
            response = await self.read_holding_registers(device_id=self.PSU_ADDR,
                                                         address=self.RD60xxRegisters.M1_V.value,
                                                         count=read_count)
            regs = response.registers
            if len(regs) != read_count:
                raise Exception("Wrong number of registered returned")

            # Prepare preset list
            new_presets = []

            # Iterate over registers
            for i in range(0, len(regs), 4):
                # Extract fields
                voltage = regs[i + 0] / voltage_scale
                current = regs[i + 1] / current_scale
                ovp = regs[i + 2] / voltage_scale
                ocp = regs[i + 3] / current_scale

                # Add tuple
                new_presets.append((voltage, current, ovp, ocp))

            # Update presets
            self._presets = new_presets

            # Update last read time
            self._presets_last_read = curr_time

    async def set_state(self, new_state:RD60xxStateSet):
        """Write new state to PSU"""

        # Query unit model to lookup scalings
        response = await self.read_holding_registers(device_id=self.PSU_ADDR,
                                                     address=self.RD60xxRegisters.MODEL.value,
                                                     count=1)
        model_inc_hw_rev = response.registers[0]
        model_exc_hw_rev = model_inc_hw_rev // 10

        # Lookup voltage, current and power scaling, with and without hardware revision
        if model_inc_hw_rev in self.MODEL_VOLTAGE_SCALINGS:
            voltage_scale = self.MODEL_VOLTAGE_SCALINGS[model_inc_hw_rev]
        else:
            voltage_scale = self.MODEL_VOLTAGE_SCALINGS.get(model_exc_hw_rev, self.DEFAULT_VOLTAGE_SCALE)
        if model_inc_hw_rev in self.MODEL_CURRENT_SCALINGS:
            current_scale = self.MODEL_CURRENT_SCALINGS[model_inc_hw_rev]
        else:
            current_scale = self.MODEL_CURRENT_SCALINGS.get(model_exc_hw_rev, self.DEFAULT_CURRENT_SCALE)

        # Split current scale
        current_scale, use_current_range = current_scale

        # Retrieve current range
        if use_current_range:
            # Query unit model to lookup current scale
            response = await self.read_holding_registers(device_id=self.PSU_ADDR,
                                                         address=self.RD60xxRegisters.CURRENT_RANGE.value,
                                                         count=1)
            current_range = response.registers[0]
            if current_range == 0:
                current_scale *= 10

        # Extract and scale values
        output_voltage_set = new_state.output_voltage_set
        if output_voltage_set is not None:
            output_voltage_set = int(output_voltage_set * voltage_scale)

        output_current_set = new_state.output_current_set
        if output_current_set is not None:
            output_current_set = int(output_current_set * current_scale)

        # Set preset
        if new_state.preset_index is not None:
            # Write register
            await self.write_register(device_id=self.PSU_ADDR, address=self.RD60xxRegisters.PRESET.value, value=new_state.preset_index)

        # Send voltage and current together if both supplied
        if output_voltage_set is not None and output_current_set is not None:
            # Write registers
            #await self.write_registers(device_id=self.PSU_ADDR, address=self.RD60xxRegisters.OUTPUT_VOLTAGE_SET.value, values=[output_voltage_set, output_current_set])
            await self.write_registers(device_id=self.PSU_ADDR, address=self.RD60xxRegisters.M0_V.value, values=[output_voltage_set, output_current_set])

        elif output_voltage_set is not None:
            # Write register
            #await self.write_register(device_id=self.PSU_ADDR, address=self.RD60xxRegisters.OUTPUT_VOLTAGE_SET.value, value=output_voltage_set)
            await self.write_register(device_id=self.PSU_ADDR, address=self.RD60xxRegisters.M0_V.value, value=output_voltage_set)

        elif output_current_set is not None:
            # Write register
            #await self.write_register(device_id=self.PSU_ADDR, address=self.RD60xxRegisters.OUTPUT_CURRENT_SET.value, value=output_current_set)
            await self.write_register(device_id=self.PSU_ADDR, address=self.RD60xxRegisters.M0_C.value, value=output_current_set)

        # Send OVP / OCP
        if new_state.ovp is not None:
            # Write register
            await self.write_register(device_id=self.PSU_ADDR, address=self.RD60xxRegisters.M0_OVP.value, value=int(new_state.ovp * voltage_scale))

        if new_state.ocp is not None:
            # Write register
            await self.write_register(device_id=self.PSU_ADDR, address=self.RD60xxRegisters.M0_OCP.value, value=int(new_state.ocp * current_scale))

        # Send output enable
        if new_state.output_enable is not None:
            # Write register
            await self.write_register(device_id=self.PSU_ADDR, address=self.RD60xxRegisters.OUTPUT_ENABLE.value, value=1 if new_state.output_enable else 0)

        # Toggle output if requested
        if new_state.output_toggle is not None and new_state.output_toggle:
            # Read register
            response = await self.read_holding_registers(device_id=self.PSU_ADDR,
                                                         address=self.RD60xxRegisters.OUTPUT_ENABLE.value,
                                                         count=1)
            value = response.registers[0]

            # Invert register
            value = 1 if value == 0 else 0

            # Write register
            await self.write_register(device_id=self.PSU_ADDR, address=self.RD60xxRegisters.OUTPUT_ENABLE.value, value=value)
