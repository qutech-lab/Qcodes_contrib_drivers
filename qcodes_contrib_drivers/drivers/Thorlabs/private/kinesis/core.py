from __future__ import annotations

import abc
import os
import pathlib
import time
import warnings
from functools import wraps, partial
from typing import Mapping, Any, List, Tuple, Iterable, Callable

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


def success_check(func):
    """Wraps functions that return a boolean success code.

    1 means success, 0 means failure."""
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

    def __init__(self, lib: str, prefix: str,
                 dll_dir: str | os.PathLike | None = None,
                 simulation: bool = False):

        self.prefix = prefix
        self.dll_dir = pathlib.Path(dll_dir or DLL_DIR)
        self.serialNo = ctypes.c_char_p()
        self.simulation = simulation

        if not lib.startswith("Thorlabs.MotionControl"):
            lib = "Thorlabs.MotionControl." + lib
        if not lib.endswith(".dll"):
            lib = lib + ".dll"
        if not (dll := self.dll_dir / lib).exists():
            raise FileNotFoundError(f'Did not find DLL {dll}')

        self.lib: ctypes.CDLL = ctypes.cdll.LoadLibrary(str(dll))
        if simulation:
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
    def build_device_list(self):
        return self.lib.TLI_BuildDeviceList()

    def load_settings(self):
        return self.get_function('LoadSettings', check_success=True)()

    def request_status(self):
        return self.get_function('RequestStatus', check_errors=True)()

    def get_position(self) -> int | float | str:
        self.request_status()
        time.sleep(self.get_polling_duration() * 1e-3)
        return self.get_function('GetPosition')()

    def move_to_position(self, val: int | str):
        return self.get_function('MoveToPosition', check_errors=True)(val)

    def get_motor_params_ext(self) -> Tuple[float, float, float]:
        stepsPerRev = ctypes.c_double()
        gearBoxRatio = ctypes.c_double()
        pitch = ctypes.c_double()
        self.get_function('GetMotorParamsExt', check_errors=True)(
            ctypes.byref(stepsPerRev),
            ctypes.byref(gearBoxRatio),
            ctypes.byref(pitch)
        )
        return stepsPerRev.value, gearBoxRatio.value, pitch.value

    def set_motor_params_ext(self, steps_per_rev: float, gearbox_ratio: float,
                             pitch: float):
        self.get_function('SetMotorParamsExt', check_errors=True)(
            ctypes.c_double(steps_per_rev),
            ctypes.c_double(gearbox_ratio),
            ctypes.c_double(pitch)
        )

    def start_polling(self, duration: int):
        return self.get_function('StartPolling', check_success=True)(duration)

    def stop_polling(self):
        return self.get_function('StopPolling')()

    def get_polling_duration(self) -> int:
        return self.get_function('PollingDuration')()

    def set_polling_duration(self, duration: int):
        self.stop_polling()
        self.start_polling(duration)

    def open(self):
        return self.get_function('Open', check_errors=True)()

    def close(self):
        self.get_function('Close')()

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
            unit_type: enums.ISCUnitType
    ) -> ctypes.c_int:
        """Convert real values to device units.

        In order to do this, the device settings must be loaded using
        :meth:`load_settings`
        """
        if isinstance(unit_type, int):
            unit_type = enums.ISCUnitType(unit_type)
        elif isinstance(unit_type, str):
            unit_type = getattr(enums.ISCUnitType, unit_type)
        elif not isinstance(unit_type, enums.ISCUnitType):
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

    def real_value_from_device_unit(self, device_unit: ctypes.c_int,
                                    unit_type: enums.ISCUnitType) -> float:
        """Convert device units to real values.

        In order to do this, the device settings must be loaded using
        :meth:`load_settings`
        """
        if isinstance(unit_type, int):
            unit_type = enums.ISCUnitType(unit_type)
        elif isinstance(unit_type, str):
            unit_type = getattr(enums.ISCUnitType, unit_type)
        elif not isinstance(unit_type, enums.ISCUnitType):
            raise TypeError('unit_type should be int, str, or ISCUnitType, '
                            f'not {type(unit_type)}')

        real_unit = ctypes.c_double()
        error_check(self.get_function('GetRealValueFromDeviceUnit'))(
            device_unit,
            ctypes.byref(real_unit),
            unit_type.value
        )
        return real_unit.value


class KinesisInstrument(Instrument, abc.ABC):
    """Qcodes Instrument subclass for Kinesis instruments.

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

    def __init__(self, name: str, dll_dir: str | pathlib.Path | None = None,
                 serial: int | None = None, simulation: bool = False,
                 metadata: Mapping[Any, Any] | None = None,
                 label: str | None = None):
        try:
            self.kinesis = ThorlabsKinesis(self.hardware_type().name,
                                           self._prefix(), dll_dir, simulation)
        except FileNotFoundError:
            # Subclass needs to handle irregular dll name
            self.kinesis = self._init_kinesis(dll_dir, simulation)

        self._initialized: bool = False

        super().__init__(name, metadata, label)

        self.add_parameter('polling_duration',
                           get_cmd=self.kinesis.get_polling_duration,
                           set_cmd=self.kinesis.set_polling_duration,
                           unit='ms')

        self.connect(serial)

    def _init_kinesis(self,
                      dll_dir: str | pathlib.Path | None,
                      simulation: bool) -> ThorlabsKinesis:
        raise NotImplementedError(f'The subclass {type(self)} should override '
                                  'the _init_kinesis() method for irregular '
                                  'dll name.')

    @classmethod
    @abc.abstractmethod
    def _prefix(cls) -> str:
        pass

    @classmethod
    @abc.abstractmethod
    def hardware_type(cls) -> enums.KinesisHWType:
        pass

    @property
    def serial(self) -> int | None:
        sn = self.kinesis.serialNo.value
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
                list_available_devices(self.kinesis.lib, self.hardware_type())
            ]
        except KinesisError:
            self._initialized = False
            raise

    def connect(self, serial: int | None, polling_duration: int = 100):
        begin_time = time.time()

        if serial is None:
            available_devices = self.list_available_devices()
            if not len(available_devices):
                raise RuntimeError(f'No {self.prefix} devices found!')
            serial = available_devices[0]

        if not self._initialized:
            error_check(self.kinesis.lib.TLI_BuildDeviceList())

        if self.connected:
            warnings.warn('Already connected to device with serial '
                          f'{self.serial}. Disconnecting.',
                          UserWarning, stacklevel=2)
            self.disconnect()

        self.kinesis.serialNo.value = str(serial).encode()
        self.kinesis.open()
        self.kinesis.start_polling(polling_duration)
        self.connect_message(begin_time=begin_time)

    def disconnect(self):
        if self.kinesis.simulation:
            self.kinesis.disable_simulation()
        if self.connected:
            self.kinesis.stop_polling()
            self.kinesis.close()
            self.kinesis.serialNo.value = None

    def get_idn(self) -> dict[str, str | None]:
        model, type, num_channels, notes, firmware, hardware, state = \
            self.kinesis.get_hw_info()
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
            devices.append((enums.KinesisHWType(hw_type_id), int(serialNo.value.split(b',')[0])))
        if len(devices) == n:
            # Found all devices already
            break

    return devices
