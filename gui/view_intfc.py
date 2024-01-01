import abc
from typing import List

class RidenPSUListEntry:
    """PSU name and identity to include in PSU list"""

    def __init__(self, identity:str, name:str, model:int, serial_no:int) -> None:
        """Construct entry"""

        self._identity = identity
        self._name = name
        self._model = model
        self._serial_no = serial_no

    @property
    def identity(self) -> str:
        return self._identity

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> int:
        return self._model

    @property
    def serial_no(self) -> int:
        return self._serial_no

    def __str__(self) -> str:
        return f"{self.name} (RD{self.model // 10} #{self.serial_no})"

class RidenPSUViewIntfc(abc.ABC):
    """View for Riden RD60xx Remote Control Interface"""

    @abc.abstractmethod
    def set_psus(self, psus:List[RidenPSUListEntry]):
        """Set PSU list box entries"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_connected(self, connected:bool):
        """Set display to indicate that PSU is connected"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_update_state(self, enabled:bool):
        """Set auto-update state"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_current_range(self, value:int):
        """Set current range in use"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_input_voltage(self, value:float):
        """Set input voltage display element"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_output_voltage_set(self, value:float):
        """Set output voltage set display element"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_output_current_set(self, value:float):
        """Set output current set display element"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_ovp(self, value:float):
        """Set over voltage protection display element"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_ocp(self, value:float):
        """Set over current protection display element"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_output_voltage_disp(self, value:float):
        """Set output voltage disp display element"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_output_power_disp(self, value:float):
        """Set output power disp display element"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_output_current_power(self, value:float):
        """Set output power disp display element"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_cc_cv(self, cc:bool):
        """Set output state"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_ovp_ocp(self, status:str):
        """Set output protection state"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_batt_state(self, batt_present:bool):
        """Set battery connection state"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_temp(self, value:float):
        """Set temperature"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_batt_ah(self, value:float):
        """Set battery amp-hours"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_batt_wh(self, value:float):
        """Set battery watt-hours"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_output_enabled(self, enabled:bool):
        """Set output enabled status"""
        raise NotImplementedError()
