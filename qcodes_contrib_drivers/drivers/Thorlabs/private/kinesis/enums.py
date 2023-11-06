import enum


class KinesisHWType(enum.Enum):
    CageRotator = 55
    FilterFlipper = 37


class MotorTypes(enum.Enum):
    """Values that represent different Motor Types."""
    NotMotor = 0
    """Not a motor."""
    DCMotor = 1
    """Motor is a DC Servo motor."""
    StepperMotor = 2
    """Motor is a Stepper Motor."""
    BrushlessMotor = 3
    """Motor is a Brushless Motor."""
    CustomMotor = 100
    """Motor is a custom motor."""


class ISCUnitType(enum.Enum):
    Distance = 0
    Velocity = 1
    Acceleration = 2


class JogModes(enum.Enum):
    JogModeUndefined = 0
    """Undefined."""
    Continuous = 1
    """Continuous jogging."""
    SingleStep = 2
    """Jog 1 step at a time."""


class StopModes(enum.Enum):
    StopModeUndefined = 0
    """Undefined."""
    Immediate = 1
    """Stops immediate."""
    Profiled = 2
    """Stops using a velocity profile."""


class TravelDirection(enum.Enum):
    TravelDirectionDisabled = 0
    """Disabled or Undefined."""
    Forwards = 1
    """Move in a Forward direction."""
    Reverse = 2
    """Move in a Backward / Reverse direction."""


class HomeLimitSwitchDirection(enum.Enum):
    """Values that represent Limit Switch Directions."""
    LimitSwitchDirectionUndefined = 0
    """Undefined."""
    ReverseLimitSwitch = 1
    """Limit switch in forward direction."""
    ForwardLimitSwitch = 1
    """Limit switch in reverse direction."""
