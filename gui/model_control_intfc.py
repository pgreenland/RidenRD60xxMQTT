import abc

class RidenPSUModelControlIntfc(abc.ABC):
    """Model / controller-esq class, managing MQTT connection and interaction between GUI and broker"""

    @abc.abstractmethod
    def set_psu(self, identity:str) -> None:
        """Set PSU to monitor / control"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_update(self, enabled:bool) -> None:
        """Set update period (auto-update enabled / disabled)"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_voltage(self, value:float) -> None:
        """Set new voltage"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_current(self, value:float) -> None:
        """Set new current"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_ovp(self, value:float) -> None:
        """Set new over-voltage protection limit"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_ocp(self, value:float) -> None:
        """Set new over-current protection limit"""
        raise NotImplementedError()

    @abc.abstractmethod
    def set_preset(self, index:int) -> None:
        """Set new preset number"""
        raise NotImplementedError()

    @abc.abstractmethod
    def toggle_output_enable(self) -> None:
        """Toggle output state"""
        raise NotImplementedError()
