class PSUState:
    """Single PSU state"""

    def __init__(self) -> None:
        """Init new state"""

        # Automatic updates disabled
        self._update_period = 0

    @property
    def update_period(self):
        return self._update_period

    @update_period.setter
    def update_period(self, value:int):
        self._update_period = value

class PSUStates:
    """Holds state which should persist across PSU connections"""

    def __init__(self) -> None:
        """Constructor"""

        # Prepare a map from serial number to state
        self._state = {}

    def get_state(self, identity:str, create:bool=True):
        """Get state for PSU (or new state if PSU is not known)"""

        # Retrieve state
        state = self._state.get(identity)

        if state is None and create:
            # Create new state
            state = PSUState()

            # Store state
            self._state[identity] = state

        return state
