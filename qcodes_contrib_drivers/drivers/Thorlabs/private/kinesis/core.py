"""Core Kinesis functionality.

New instruments should inherit from :class:`KinesisInstrument` or one of
the specialized sublasses (eg :class:`isc.KinesisISCInstrument`). See
their docstrings for instructions.
"""
from __future__ import annotations

import os
import pathlib
import time
import warnings
from enum import EnumMeta
from functools import partial, wraps
from typing import Any, Callable, Iterable, List, Literal, Mapping, Tuple
from typing import Sequence, TypeVar

from typing_extensions import ParamSpec

from qcodes import Instrument
from . import enums

try:
    import ctypes.wintypes
except ImportError:
    import ctypes
    from types import ModuleType

    ctypes.wintypes = ModuleType('wintypes')
    ctypes.wintypes.WORD = ctypes.c_ushort
    ctypes.wintypes.DWORD = ctypes.c_ulong

DLL_DIR = r"C:\Program Files\Thorlabs\Kinesis"

ERROR_CODES = {
    # Errors generated from the FTDI communications module or
    # supporting code
    0: 'FT_OK',
    1: 'FT_InvalidHandle',
    2: 'FT_DeviceNotFound',
    3: 'FT_DeviceNotOpened',
    4: 'FT_IOError',
    5: 'FT_InsufficientResources',
    6: 'FT_InvalidParameter',
    7: 'FT_DeviceNotPresent',
    8: 'FT_IncorrectDevice',
    # Errors generated by the device libraries
    16: 'FT_NoDLLLoaded',
    17: 'FT_NoFunctionsAvailable',
    18: 'FT_FunctionNotAvailable',
    19: 'FT_BadFunctionPointer',
    20: 'FT_GenericFunctionFail',
    21: 'FT_SpecificFunctionFail',
    # General errors generated by all DLLs
    0x20: 'TL_ALREADY_OPEN',
    0x21: 'TL_NO_RESPONSE',
    0x22: 'TL_NOT_IMPLEMENTED',
    0x23: 'TL_FAULT_REPORTED',
    0x24: 'TL_INVALID_OPERATION',
    0x28: 'TL_DISCONNECTING',
    0x29: 'TL_FIRMWARE_BUG',
    0x2A: 'TL_INITIALIZATION_FAILURE',
    0x2B: 'TL_INVALID_CHANNEL',
    # Motor-specific errors generated by the Motor DLLs
    0x25: 'TL_UNHOMED',
    0x26: 'TL_INVALID_POSITION',
    0x27: 'TL_INVALID_VELOCITY_PARAMETER',
    0x2C: 'TL_CANNOT_HOME_DEVICE',
    0x2D: 'TL_JOG_CONTINUOUS_MODE',
    0x2E: 'TL_NO_MOTOR_INFO',
    0x2F: 'TL_CMD_TEMP_UNAVAILABLE'
}

ERROR_MESSAGES = {
    'FT_OK': 'Success',
    'FT_InvalidHandle': 'The FTDI functions have not been initialized.',
    'FT_DeviceNotFound': 'The Device could not be found. This can be '
                         'generated if the function TLI_BuildDeviceList() '
                         'has not been called.',
    'FT_DeviceNotOpened': 'The Device must be opened before it can be '
                          'accessed. See the appropriate Open function '
                          'for your device.',
    'FT_IOError': 'An I/O Error has occured in the FTDI chip.',
    'FT_InsufficientResources': 'There are Insufficient resources to run '
                                'this application.',
    'FT_InvalidParameter': 'An invalid parameter has been supplied to the '
                           'device.',
    'FT_DeviceNotPresent': 'The Device is no longer present. The device '
                           'may have been disconnected since the last '
                           'TLI_BuildDeviceList() call.',
    'FT_IncorrectDevice': 'The device detected does not match that '
                          'expected.',
    'FT_NoDLLLoaded': 'The library for this device could not be found.',
    'FT_NoFunctionsAvailable': 'No functions available for this device.',
    'FT_FunctionNotAvailable': 'The function is not available for this '
                               'device.',
    'FT_BadFunctionPointer': 'Bad function pointer detected.',
    'FT_GenericFunctionFail': 'The function failed to complete '
                              'succesfully.',
    'FT_SpecificFunctionFail': 'The function failed to complete '
                               'succesfully',
    'TL_ALREADY_OPEN': 'Attempt to open a device that was already open.',
    'TL_NO_RESPONSE': 'The device has stopped responding.',
    'TL_NOT_IMPLEMENTED': 'This function has not been implemented.',
    'TL_FAULT_REPORTED': 'The device has reported a fault.',
    'TL_INVALID_OPERATION': 'The function could not be completed at this '
                            'time.',
    'TL_DISCONNECTING': 'The function could not be completed because the '
                        'device is disconnected.',
    'TL_FIRMWARE_BUG': 'The firmware has thrown an error.',
    'TL_INITIALIZATION_FAILURE': 'The device has failed to initialize.',
    'TL_INVALID_CHANNEL': 'An Invalid channel address was supplied.',
    'TL_UNHOMED': 'The device cannot perform this function until it has '
                  'been Homed.',
    'TL_INVALID_POSITION': 'The function cannot be performed as it would '
                           'result in an illegal position.',
    'TL_INVALID_VELOCITY_PARAMETER': 'An invalid velocity parameter was '
                                     'supplied. The velocity must be '
                                     'greater than zero.',
    'TL_CANNOT_HOME_DEVICE': 'This device does not support Homing. Check '
                             'the Limit switch parameters are correct.',
    'TL_JOG_CONTINOUS_MODE': 'An invalid jog mode was supplied for the '
                             'jog function.',
    'TL_NO_MOTOR_INFO': 'There is no Motor Parameters available to '
                        'convert Real World Units.',
    'TL_CMD_TEMP_UNAVAILABLE': 'Command temporarily unavailable, Device '
                               'may be busy.'
}

P = ParamSpec('P')
T = TypeVar('T')


def to_enum(arg: EnumMeta | str | int, enum: EnumMeta):
    """Return an instance of type enum for a given name, value, or the
    enum itself."""
    if isinstance(arg, str):
        # Try to catch at least single-noun names that are not capitalized.
        arg = getattr(enum, arg.capitalize())
    elif isinstance(arg, int):
        arg = enum(arg)
    return arg


def register_prefix(prefixes: Sequence[str]) -> Callable:
    """Registers a warpped DLL function for a given Kinesis device.

    prefixes is a sequence of string identifier prefixes that are
    returned by a KinesisInstrument's :meth:`_prefix` classmethod.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        func.__prefixes = prefixes
        return func

    return decorator


def success_check(func):
    """Wraps functions that return a boolean success code.

    1 means success, 0 means failure.
    """

    @wraps(func)
    def wrapped(*args, **kwargs):
        if not func(*args, **kwargs):
            raise KinesisError('Unspecified failure.')

    return wrapped


def error_check(func):
    """Wraps functions that return an integer error code."""

    @wraps(func)
    def wrapped(*args, **kwargs):
        code = func(*args, **kwargs)
        if (status := ERROR_CODES.get(code)) != 'FT_OK':
            raise KinesisError(f'{status}: {ERROR_MESSAGES[status]}')

    return wrapped


class ThorlabsKinesis:
    """The interface to Kinesis dlls."""

    def __init__(self, lib: str, prefix: str,
                 dll_dir: str | os.PathLike | None = '',
                 simulation: bool = False):

        if not lib.startswith("Thorlabs.MotionControl"):
            lib = "Thorlabs.MotionControl." + lib
        if not lib.endswith(".dll"):
            lib = lib + ".dll"

        self.prefix = prefix
        self.lib: ctypes.CDLL = ctypes.cdll.LoadLibrary(
            os.path.join(dll_dir if dll_dir is not None else DLL_DIR, lib)
        )
        self.serialNo = ctypes.c_char_p()
        self.simulation = simulation

        if self.simulation:
            self.enable_simulation()

        self.build_device_list()

    @staticmethod
    def parse_fw_version(fw: int) -> str:
        parts = [f'{i:02d}' for i in fw.to_bytes(length=4, byteorder='big')]
        return '.'.join(parts).lstrip('0.')

    def get_function(self, name: str, check_errors: bool = False,
                     check_success: bool = False) -> Callable:
        """Convenience method for getting a function from the dll.

        If check_errors or check_success is True, the return value of
        the function will be checked for the respective codes.
        """
        try:
            func = partial(getattr(self.lib, f'{self.prefix}_{name}'),
                           self.serialNo)
        except AttributeError as err:
            raise AttributeError(f'Function {self.prefix}_{name} not found in '
                                 f'dll {self.lib}') from err
        if check_errors:
            func = error_check(func)
        if check_success:
            func = success_check(func)
        return func

    def enable_simulation(self) -> None:
        """Initialise a connection to the simulation manager, which must
        already be running."""
        self.lib.TLI_InitializeSimulations()

    def disable_simulation(self) -> None:
        """Uninitialize a connection to the simulation manager, which
        must be running."""
        self.lib.TLI_UninitializeSimulations()

    @error_check
    def build_device_list(self) -> None:
        """Build the DeviceList.

        This function builds an internal collection of all devices found
        on the USB that are not currently open.

        Note:
             If a device is open, it will not appear in the list until
             the device has been closed.

        """
        return self.lib.TLI_BuildDeviceList()

    def load_settings(self) -> None:
        """Update device with stored settings."""
        self.get_function('LoadSettings', check_success=True)()

    def request_status(self) -> None:
        """Request position and status bits.

        This needs to be called to get the device to send it's current
        status.

        Note:
            This is called automatically if Polling is enabled for the
            device using :meth:`start_polling`.

        """
        self.get_function('RequestStatus', check_errors=True)()

    def request_status_bits(self) -> None:
        """Request the status bits which identify the current motor
        state.

        This needs to be called to get the device to send it's current
        status bits.

        Note:
            This is called automatically if Polling is enabled for the
            device using :meth:`start_polling`.

        """
        self.get_function('RequestStatusBits', check_errors=True)()

    def get_status_bits(self) -> int:
        """Get the current status bits.

        This returns the latest status bits received from the device.
        To get new status bits, use :meth:`request_status` or use the
        polling functions, :meth:`start_polling`.

        Returns:
            The status bits from the device. See the API manual for more
            information on their meaning.

        """
        self.request_status_bits()
        function = self.get_function('GetStatusBits')
        function.restype = ctypes.wintypes.DWORD
        return function()

    @register_prefix(['ISC', 'CC'])
    def reset_rotation_modes(self):
        """Reset the rotation modes for a rotational device."""
        self.get_function('ResetRotationModes', check_errors=True)()

    @register_prefix(['ISC', 'CC'])
    def set_rotation_modes(self, mode: enums.MovementModes | str | int,
                           direction: enums.MovementDirections | str | int):
        """Set the rotation modes for a rotational device.

        Args:
            mode: The rotation mode.
            direction: The rotation direction when moving between two
            angles.
        """
        self.get_function('SetRotationModes', check_errors=True)(
            to_enum(mode, enums.MovementModes).value,
            to_enum(direction, enums.MovementDirections).value
        )

    def get_jog_mode(self) -> Tuple[enums.JogModes, enums.StopModes]:
        """Gets the jog mode.

        Returns:
            jog_mode
            stop_mode

        """
        mode = ctypes.c_short()
        stopMode = ctypes.c_short()
        self.get_function('GetJogMode', check_errors=True)(
            ctypes.byref(mode),
            ctypes.byref(stopMode)
        )
        return enums.JogModes(mode.value), enums.StopModes(stopMode.value)

    def set_jog_mode(self,
                     jog_mode: enums.JogModes | int | str,
                     stop_mode: enums.StopModes | int | str):
        """Sets the jog mode.

        Args:
            jog_mode: The jog mode.
            stop_mode: The StopMode.

        """
        self.get_function('SetJogMode', check_errors=True)(
            to_enum(jog_mode, enums.JogModes),
            to_enum(stop_mode, enums.StopModes)
        )

    @register_prefix(['FF', 'ISC', 'CC'])
    def identify(self) -> None:
        """Sends a command to the device to make it identify iteself."""
        self.get_function('Identify')()

    @register_prefix(['FF', 'ISC', 'CC'])
    def get_number_positions(self) -> int:
        """Get number of positions.

        The GetNumberPositions function will get the maximum position
        reachable by the device. The motor may need to be Homed before
        this parameter can be used.
        """
        return int(self.get_function('GetNumberPositions')())

    @register_prefix(['FF', 'ISC', 'CC'])
    def get_position(self) -> int | float | str:
        """Get the current position.

        The current position is the last recorded position.
        The current position is updated either by the polling mechanism
        or by calling RequestPosition or RequestStatus.

        Returns:
            The current position.
        """
        self.request_status()
        time.sleep(self.get_polling_duration() * 1e-3)
        return self.get_function('GetPosition')()

    @register_prefix(['FF', 'ISC', 'CC'])
    def move_to_position(self, position: int | str,
                         block: bool = False) -> None:
        """Move the device to the specified position (index).

        The motor may need to be Homed before a position can be set. See
        Positioning for more detail.

        Args:
            position:
                The required position. must be 1 or 2 for the filter
                flipper or in device units else.
            block:
                Block the interpreter until the target position is
                reached.

        """
        self.get_function('MoveToPosition', check_errors=True)(position)

        while block and self.is_moving():
            time.sleep(50e-3)

    @register_prefix(['ISC', 'CC'])
    def move_at_velocity(
            self,
            direction: enums.TravelDirection | str | int
    ) -> None:
        """Start moving at the current velocity in the specified
        direction."""
        self.get_function('MoveAtVelocity', check_errors=True)(
            to_enum(direction, enums.TravelDirection).value
        )

    @register_prefix(['ISC', 'CC'])
    def move_relative(self, displacement: int):
        """Move the motor by a relative amount.

        Args:
            displacement: Signed displacement in Device Units.

        """
        self.get_function('MoveRelative', check_errors=True)(displacement)

    @register_prefix(['FF', 'ISC', 'CC'])
    def is_moving(self) -> bool:
        """If the device is moving or not.

        Note that for the FilterFlipper devices, this is always false.
        """
        status = self.get_status_bits()
        return bool((status & 0x00000010) | (status & 0x00000020))

    @register_prefix(['ISC', 'CC'])
    def get_vel_params(self) -> Tuple[int, int]:
        """Gets the move velocity parameters.

        Returns:
            acceleration: The new acceleration value in Device Units.
            max_velocity: The new maximum velocity value in Device Units.

        """
        acceleration = ctypes.c_int()
        maxVelocity = ctypes.c_int()
        self.get_function('GetVelParams', check_errors=True)(
            ctypes.byref(acceleration),
            ctypes.byref(maxVelocity)
        )
        return acceleration.value, maxVelocity.value

    @register_prefix(['ISC', 'CC'])
    def set_vel_params(self, acceleration: int, max_velocity: int):
        """Sets the move velocity parameters.

        Args:
            acceleration: The new acceleration value in Device Units.
            max_velocity: The new maximum velocity value in Device Units.

        """
        self.get_function('SetVelParams', check_errors=True)(acceleration,
                                                             max_velocity)

    @register_prefix(['FF'])
    def get_transit_time(self) -> int:
        """Gets the transit time.

        Returns:
            The transit time in milliseconds, range 300 to 2800 ms.
        """
        return self.get_function('GetTransitTime')()

    @register_prefix(['FF'])
    def set_transit_time(self, transit_time: int) -> None:
        """Sets the transit time.

        Args:
             transit_time: The transit time in milliseconds, range 300
             to 2800 ms.
        """
        self.get_function('SetTransitTime', check_errors=True)(transit_time)

    @register_prefix(['ISC', 'CC'])
    def get_motor_params_ext(self) -> Tuple[float, float, float]:
        """Gets the motor stage parameters.

        These parameters, when combined define the stage motion in terms
        of Real World Units. (mm or degrees) The real world unit is
        defined from stepsPerRev * gearBoxRatio / pitch.
        """
        stepsPerRev = ctypes.c_double()
        gearBoxRatio = ctypes.c_double()
        pitch = ctypes.c_double()
        self.get_function('GetMotorParamsExt', check_errors=True)(
            ctypes.byref(stepsPerRev),
            ctypes.byref(gearBoxRatio),
            ctypes.byref(pitch)
        )
        return stepsPerRev.value, gearBoxRatio.value, pitch.value

    @register_prefix(['ISC', 'CC'])
    def set_motor_params_ext(self, steps_per_rev: float, gearbox_ratio: float,
                             pitch: float) -> None:
        """Sets the motor stage parameters.

        These parameters, when combined define the stage motion in terms
        of Real World Units. (mm or degrees) The real world unit is
        defined from stepsPerRev * gearBoxRatio / pitch.
        """
        self.get_function('SetMotorParamsExt', check_errors=True)(
            ctypes.c_double(steps_per_rev),
            ctypes.c_double(gearbox_ratio),
            ctypes.c_double(pitch)
        )

    def start_polling(self, duration: int) -> None:
        """Starts the internal polling loop which continuously requests
        position and status."""
        self.get_function('StartPolling', check_success=True)(duration)

    def stop_polling(self) -> None:
        """Stops the internal polling loop."""
        self.get_function('StopPolling')()

    def get_polling_duration(self) -> int:
        """Gets the polling loop duration."""
        return self.get_function('PollingDuration')()

    def set_polling_duration(self, duration: int) -> None:
        """Stops polling and starts it again with given duration."""
        self.stop_polling()
        self.start_polling(duration)

    def open(self) -> None:
        """Open the device for communications."""
        self.get_function('Open', check_errors=True)()

    def close(self) -> None:
        """Disconnect and close the device."""
        self.get_function('Close')()

    @register_prefix(['ISC', 'CC'])
    def disable_channel(self) -> None:
        """Disable the channel so that motor can be moved by hand.

        When disabled power is removed from the motor and it can be
        freely moved.
        """
        self.get_function('DisableChannel', check_errors=True)()

    @register_prefix(['ISC', 'CC'])
    def enable_channel(self) -> None:
        """Enable channel for computer control.

        When enabled power is applied to the motor so it is fixed in
        position.
        """
        self.get_function('EnableChannel', check_errors=True)()

    @register_prefix(['ISC', 'CC'])
    def stop(self, mode: enums.StopModes | int | str = 'Profiled') -> None:
        """Stop the current move using the current velocity profile."""
        mode = to_enum(mode, enums.StopModes)
        if mode == enums.StopModes.Immediate:
            self.get_function('StopImmediate', check_errors=True)()
        elif mode == enums.StopModes.Profiled:
            self.get_function('StopProfiled', check_errors=True)()
        else:
            raise ValueError('Invalid profile')

    @register_prefix(['ISC', 'CC'])
    def can_home(self) -> bool:
        """Can the device perform a Home."""
        return bool(self.get_function('CanHome')())

    @register_prefix(['ISC', 'CC'])
    def needs_homing(self) -> bool:
        """Can this device be moved without Homing."""
        return not bool(self.get_function('CanMoveWithoutHomingFirst')())

    @register_prefix(['FF', 'ISC', 'CC'])
    def home(self) -> None:
        """Home the device.

        Homing the device will set the device to a known state and
        determine the home position, see Homing for more detail.
        """
        self.get_function('Home', check_errors=True)()

    @register_prefix(['FF', 'ISC', 'CC'])
    def get_hw_info(self) -> Tuple[str, int, int, str, str, int, int]:
        modelNo = ctypes.create_string_buffer(64)
        type = ctypes.wintypes.WORD()
        numChannels = ctypes.wintypes.WORD()
        notes = ctypes.create_string_buffer(64)
        firmwareVersion = ctypes.wintypes.DWORD()
        hardwareVersion = ctypes.wintypes.WORD()
        modificationState = ctypes.wintypes.WORD()
        self.get_function('GetHardwareInfo', check_errors=True)(
            modelNo, 64,
            ctypes.byref(type),
            ctypes.byref(numChannels),
            notes, 64,
            ctypes.byref(firmwareVersion),
            ctypes.byref(hardwareVersion),
            ctypes.byref(modificationState)
        )
        return (modelNo.value.decode('utf-8'),
                type.value,
                numChannels.value,
                notes.value.decode('utf-8'),
                self.parse_fw_version(firmwareVersion.value),
                hardwareVersion.value,
                modificationState.value)

    def device_unit_from_real_value(
            self,
            real_unit: float,
            unit_type: enums.ISCUnitType | int | str
    ) -> ctypes.c_int:
        """Convert real values to device units.

        In order to do this, the device settings must be loaded using
        :meth:`load_settings`.
        """
        unit_type = to_enum(unit_type, enums.ISCUnitType)
        if not isinstance(unit_type, enums.ISCUnitType):
            raise TypeError('unit_type should be int, str, or ISCUnitType, '
                            f'not {type(unit_type)}')

        device_unit = ctypes.c_int()
        # Documentation says success is returned, but actually the error code
        self.get_function('GetDeviceUnitFromRealValue', check_errors=True)(
            ctypes.c_double(real_unit),
            ctypes.byref(device_unit),
            unit_type.value,
        )
        return device_unit

    def real_value_from_device_unit(
            self,
            device_unit: ctypes.c_int,
            unit_type: enums.ISCUnitType | int | str
    ) -> float:
        """Convert device units to real values.

        In order to do this, the device settings must be loaded using
        :meth:`load_settings`
        """
        unit_type = to_enum(unit_type, enums.ISCUnitType)
        if not isinstance(unit_type, enums.ISCUnitType):
            raise TypeError('unit_type should be int, str, or ISCUnitType, '
                            f'not {type(unit_type)}')

        real_unit = ctypes.c_double()
        error_check(self.get_function('GetRealValueFromDeviceUnit'))(
            device_unit,
            ctypes.byref(real_unit),
            unit_type.value
        )
        return real_unit.value


class KinesisInstrument(Instrument):
    """Base class for Qcodes Kinesis instruments.

    A subclass declaration requires two mandatory keyword arguments:

        prefix (str):
            The Kinesis DLL function prefix for this hardware type
        hardware_type (:class:`enums.HardwareType`):
            The instrument hardware type id (an integer enumeration).

    To automatically forward common DLL methods, they should be marked
    with the above prefix and the @register_prefix decorator in
    :class:`ThorlabsKinesis`. This will expose them in the subclass.

    Args:
        name:
            An identifier for this instrument.
        dll_dir (optional):
            The directory where the kinesis dlls reside.
        serial (optional):
            The serial number of the device to connect to. If omitted,
            the first available device found will be used. For a list
            of all available devices, use
            :meth:`list_available_devices` on an existing instance or
            :func:`qcodes_contrib_drivers.drivers.Thorlabs.private.kinesis.core.list_available_devices`.
        simulation (optional):
            Enable the Kinesis simulator mode. Note that the serial
            number assigned to the simulated device should be given
            since otherwise the first available device will be
            connected (which might not be a simulated but a real one).
        metadata (optional):
            Additional static metadata.
        label (optional):
            Nicely formatted name of the instrument.

    """

    def __init__(self, name: str, dll_dir: str | pathlib.Path | None = '',
                 serial: int | None = None, simulation: bool = False,
                 polling: int = 200, home: bool = False,
                 metadata: Mapping[Any, Any] | None = None,
                 label: str | None = None):
        if self._prefix is None or self.hardware_type is None:
            raise NotImplementedError('Incorrectly implemented subclass. '
                                      'Needs to be declared with prefix and '
                                      'hardware_type arguments.')

        try:
            self._kinesis = ThorlabsKinesis(self.hardware_type.name,
                                            self._prefix, dll_dir, simulation)
        except FileNotFoundError:
            # Subclass needs to handle irregular dll name
            self._kinesis = self._init_kinesis(dll_dir, simulation)

        self._initialized: bool = False

        super().__init__(name, metadata, label)

        self.add_parameter('polling_duration',
                           get_cmd=self._kinesis.get_polling_duration,
                           set_cmd=self._kinesis.set_polling_duration,
                           unit='ms')

        self.connect(serial, polling)

        if home:
            if self._kinesis.can_home():
                self._kinesis.home()
            else:
                raise RuntimeError('Device `{}` is not homeable')

    def __init_subclass__(cls,
                          prefix: str | None = None,
                          hardware_type: enums.KinesisHWType | None = None,
                          **kwargs):
        super().__init_subclass__(**kwargs)

        cls._prefix = prefix
        """The prefix of DLL functions."""
        cls.hardware_type = hardware_type
        """The hardware type identifier (an integer enumeration)."""

        def is_registered_method(item) -> bool:
            key, val = item
            return callable(val) and prefix in getattr(val, '__prefixes', [])

        # Forward functions marked by @register_prefix in ThorlabsKinesis
        for name, meth in filter(is_registered_method,
                                 ThorlabsKinesis.__dict__.items()):
            def make_wrapper(method):
                # Outer wrapper required to avoid closure problems.
                @wraps(method)
                def wrapped(self, *args, **kw):
                    return method(getattr(self, '_kinesis'), *args, **kw)

                return wrapped

            setattr(cls, name, make_wrapper(meth))

    def _init_kinesis(self,
                      dll_dir: str | pathlib.Path | None,
                      simulation: bool) -> ThorlabsKinesis:
        raise NotImplementedError(f'The subclass {type(self)} should override '
                                  'the _init_kinesis() method for irregular '
                                  'dll name.')

    @property
    def serial(self) -> int | None:
        sn = self._kinesis.serialNo.value
        if sn is not None:
            return int(sn.decode())
        return None

    @property
    def connected(self) -> bool:
        return self.serial is not None

    def list_available_devices(self) -> List[int]:
        self._initialized = True
        try:
            return [
                serial for _, serial in
                list_available_devices(self._kinesis.lib, self.hardware_type)
            ]
        except KinesisError:
            self._initialized = False
            raise

    def connect(self, serial: int | None, polling_duration: int = 100):
        begin_time = time.time()

        if serial is None:
            available_devices = self.list_available_devices()
            if not len(available_devices):
                raise RuntimeError(f'No {self._prefix} devices found!')
            serial = available_devices[0]

        if not self._initialized:
            error_check(self._kinesis.lib.TLI_BuildDeviceList())

        if self.connected:
            warnings.warn('Already connected to device with serial '
                          f'{self.serial}. Disconnecting.',
                          UserWarning, stacklevel=2)
            self.disconnect()

        self._kinesis.serialNo.value = str(serial).encode()
        self._kinesis.open()
        self._kinesis.start_polling(polling_duration)
        # Update the device with stored settings. This is necessary to be able
        # to convert units since there are specific formulae for each motor
        # taking into account Gearing, Pitch, Steps Per Revolution etc.
        self._kinesis.load_settings()
        self.connect_message(begin_time=begin_time)

    def disconnect(self):
        if self._kinesis.simulation:
            self._kinesis.disable_simulation()
        if self.connected:
            self._kinesis.stop_polling()
            self._kinesis.close()
            self._kinesis.serialNo.value = None

    def get_idn(self) -> dict[str, str | None]:
        model, type, num_channels, notes, firmware, hardware, state = \
            self._kinesis.get_hw_info()
        return {'vendor': 'Thorlabs', 'model': model, 'firmware': firmware,
                'serial': str(self.serial)}

    def close(self):
        self.disconnect()
        super().close()


class KinesisError(Exception):
    """An error raised by a Kinesis DLL."""


def list_available_devices(
        lib: str | os.PathLike | ctypes.CDLL | None = None,
        hardware_type: Iterable[enums.KinesisHWType] | enums.KinesisHWType | None = None
) -> List[Tuple[enums.KinesisHWType, int]]:
    """Discover and list available Kinesis devices.

    Args:
        lib: Either the path to a Kinesis dll or a CDLL instance.
        hardware_type: List only devices of a given type.

    Returns:
        A list of two-tuples (hardware_type_id, serial_number).

    """
    if not isinstance(lib, ctypes.CDLL):
        if lib is None:
            lib = DLL_DIR

        if not isinstance(lib, pathlib.Path):
            lib = pathlib.Path(lib)

        if lib.is_dir():
            lib /= 'Thorlabs.MotionControl.DeviceManager.dll'

        lib = ctypes.cdll.LoadLibrary(str(lib))

    error_check(lib.TLI_BuildDeviceList())
    n: int = lib.TLI_GetDeviceListSize()

    if not n:
        return []

    if hardware_type is None:
        # Search for all models
        hw_type_ids = list(range(1, 101))
    elif isinstance(hardware_type, Iterable):
        # Only search for devices of the passed hardware type (model)
        hw_type_ids = [hw.value for hw in hardware_type]
    else:
        hw_type_ids = [hardware_type.value]

    devices = []
    for hw_type_id in hw_type_ids:
        # char array, 8 bytes for serial number, 1 for delimiter, plus 1
        # surplus needed, apparently. Since the function returns all serials
        # of a given hardware type, the char buffer needs to be large enough
        # to accomodate the worst case (all devices are of this hardware type)
        serialNo = (ctypes.c_char * (8 * n + 1 + 1))()

        error_check(lib.TLI_GetDeviceListByTypeExt)(
            ctypes.byref(serialNo),
            ctypes.wintypes.DWORD(8 * n + 1 + 1),
            hw_type_id
        )
        if serialNo.value:
            devices.append((enums.KinesisHWType(hw_type_id),
                            int(serialNo.value.split(b',')[0])))
        if len(devices) == n:
            # Found all devices already
            break

    return devices