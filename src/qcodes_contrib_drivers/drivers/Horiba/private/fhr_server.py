from __future__ import annotations

import enum
import logging
from collections.abc import Callable
from ctypes import (byref, Structure, c_ulong, c_char, c_int, c_uint, c_double, sizeof,
                    create_string_buffer)
from pathlib import Path
from typing import Tuple, Concatenate, TypeVar, ParamSpec, Any

from msl.loadlib import Server32

try:
    import wintypes
except ImportError:
    import ctypes
    from types import ModuleType

    wintypes = ModuleType('wintypes')
    wintypes.DWORD = c_ulong

T = TypeVar('T')
P = ParamSpec('P')

LOG = logging.getLogger(__name__)
# Uncomment the line below to log (cannot control the logger from the
# client since the server runs on a different executable).
logging.basicConfig(filename=Path.home() / 'fhr.log', level=logging.DEBUG)

name_type = c_char * 30


# HJYFHR_ReadSectionIni Firmware section
class Firmware(Structure):
    _fields_ = [('VersionNumber', ctypes.c_int),
                ('SerialNumber', c_int)]


# HJYFHR_ReadSectionIni Port section
class Port(Structure):
    _fields_ = [('ComPort', c_int),
                ('BaudRate', c_int),
                ('Timeout', c_int)]


# HJYFHR_ReadSectionIni Spectrometer section
class Spectrometer(Structure):
    _fields_ = [('Focal', c_double),
                ('CoefficientOfAngle', c_double),
                ('Board', c_int),
                ('SpeedMin', c_int),
                ('SpeedMax', c_int),
                ('Acceleration', c_int),
                ('Backlash', c_int),
                ('MotorStepUnit', c_int),
                ('Reverse', c_int),
                ('GratingNumber', c_int),
                ('SlitNumber', c_int),
                ('UseFilter', c_int),
                ('MirrorNumber', c_int),
                ('UseShutter', c_int)]


# HJYFHR_ReadSectionIni Gratings section
class Grating(Structure):
    _fields_ = [('Name', name_type),
                ('Value', c_int),
                ('AddrAxe', c_int),
                ('Offset', c_int),
                ('Shift', c_int),
                ('MinNm', c_int),
                ('MaxNm', c_int),
                ('CoefficientOfLinearity', c_double)]


# HJYFHR_ReadSectionIni Slits section
class Slit(Structure):
    _fields_ = [('Name', name_type),
                ('AddrAxe', c_int),
                ('Offset', c_int),
                ('Minum', c_int),
                ('Maxum', c_int),
                ('Coeffum', c_double),
                ('SpeedMin', c_int),
                ('SpeedMax', c_int),
                ('Acceleration', c_int),
                ('Backlash', c_int),
                ('MotorStepUnit', c_int),
                ('Reverse', c_int)]


# HJYFHR_ReadSectionIni Mirrors and Shutter section
class DC(Structure):
    _fields_ = [('Name', name_type),
                ('AddrAxe', c_int),
                ('Delayms', c_int),
                ('DutyCyclePercent', c_int)]


# HJYFHR_ReadSectionIni Fiilters section
class Filter(Structure):
    _fields_ = [('Name', name_type * 6),
                ('AddrAxe', c_int),
                ('Offset', c_int),
                ('Delta', c_int),
                ('SpeedMin', c_int),
                ('SpeedMax', c_int),
                ('Acceleration', c_int),
                ('Backlash', c_int),
                ('MotorStepUnit', c_int),
                ('Reverse', c_int)]


# HJYFHR_SetSetup grating, slit and filter
class SetupMotor(Structure):
    _fields_ = [
        ("Size", c_uint),  # This structure size (=28)
        ("MinSpeed", c_int),  # Minimal speed
        ("MaxSpeed", c_int),  # Maximal speed
        ("Ramp", c_int),  # Acceleration
        ("Backlash", c_int),  # Backlash
        ("Step", c_int),
        # Operation mode (Step = 1 in steps, Step = 0 position in pm only for gratings)
        ("Revers", c_int),  # Rotation direction (=0 - direct, =1 - inverse)
    ]


# HJYFHR_SetSetup shutter and mirror
class SetupDC(Structure):
    _fields_ = [
        ("Size", c_uint),  # This structure size (=12)
        ("Delayms", c_int),  # Delay in milliseconds
        ("DutyCyclePercent", c_int),  # Duty cycle percentage
    ]


# HJYFHR_Initialization grating
class InitGrating(Structure):
    _fields_ = [
        ("Size", c_uint),  # This structure size (=12)
        ("Offset", c_int),  # Number of steps between mechanical and optical 0
        ("Shift", c_int),  # Shift of the offset
    ]


# HJYFHR_Initialization slit and filter
class InitSlitFilter(Structure):
    _fields_ = [
        ("Size", c_uint),  # This structure size (=8)
        ("Offset", c_int),  # Offset compared to 0 position
    ]


# HJYFHHR_GetStatus grating, slit, filter, shutter and mirror
class Status(Structure):
    _fields_ = [
        ("MotorState", c_int),  # Motor state (ready/busy/timeout)
        ("SwitchState", c_int),  # Switch state (none/lowswitch/bothswitches)
        ("Position", c_int),
        # Position state (lostPosition/NoReadValue/position in step or pm only for grating)
    ]


# HJYFHR_Scan structure for gratings
class Scan(Structure):
    _fields_ = [
        ("FromPosition", c_int),  # Start position
        ("ToPosition", c_int),  # End position
        ("Inc", c_int),  # Increment (in step or pm)
        ("Wait", c_int),  # Wait time between increments in ms
    ]


# HJYFHR_SetCalibration and HJYFHR_GetCalibration structure for grating
class CoeffLinear(Structure):
    _fields_ = [
        ("Size", c_uint),  # This structure size (=96)
        ("Count", c_uint),  # Number of gratings
        ("Angle", c_double),  # CoefficientOfAngle from spectrometer section
        ("Coeff", c_double * 10),  # Coeff array [10] (range 0..9)
    ]


class ErrorCode(enum.IntEnum):
    invalid_dispatcher_name = 1
    invalid_function_name = 2
    invalid_parameter = 3
    connection_error = 4
    connection_timeout = 5
    wrong_result = 6
    abort = 7
    invalid_handle = 8
    force_32bit = 0xFFFFFF
    exception = 800
    init_necessary = 50
    invalid_addr_axe = 51
    negative_value = 52
    outof_range_value_nm = 53
    outof_range_value_um = 54
    lambda_not_available = 55
    set_set_up_not_done = 56
    outof_range0or1 = 57
    value_out_of_range_setup = 58
    value_out_of_range_init = 59
    value_coeff_out_of_range = 60
    value_shift_out_of_range = 61
    ini_memory_alloc = 999
    ini_firm_ware_para_not_found = 1100
    ini_port_para_not_found = 1101
    ini_spectrometer_not_found = 1102
    ini_grating_not_found = 1103
    ini_slit_not_found = 1104
    ini_mirror_not_found = 1105
    ini_shutter_not_found = 1106
    ini_filter_not_found = 1107


class Dispatcher(enum.StrEnum):
    Grating1 = enum.auto()
    Grating2 = enum.auto()
    Grating3 = enum.auto()
    Grating4 = enum.auto()
    Grating5 = enum.auto()
    Grating6 = enum.auto()
    Grating7 = enum.auto()
    Grating8 = enum.auto()
    Grating9 = enum.auto()
    Grating10 = enum.auto()
    Slit1 = enum.auto()
    Slit2 = enum.auto()
    Slit3 = enum.auto()
    Slit4 = enum.auto()
    Mirror1 = enum.auto()
    Mirror2 = enum.auto()
    Filters1 = enum.auto()
    Shutter = enum.auto()
    notDefined = enum.auto()


class FHRServer(Server32):

    def __init__(self, host, port, dll_dir='', filename='FHRCustomer'):
        path = str(Path(dll_dir, filename).with_suffix('.dll'))

        LOG.info('Initializing FHRServer.')
        LOG.debug(f'host = {host}')
        LOG.debug(f'port = {port}')
        LOG.debug(f'path = {path}')

        super().__init__(path, 'cdll', host, port)

    @staticmethod
    def check_error(func: Callable[P, Concatenate[int, T]]) -> Callable[P, T]:
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
            code, res = func(*args, **kwargs)
            try:
                code = ErrorCode(code)
            except ValueError:
                pass
            else:
                error = RuntimeError(f'FHR Error: {repr(ErrorCode(code))}')
                LOG.error('FHR error', exc_info=error)
                raise error

            return res

        return wrapped

    @check_error
    def read_section_ini(self, section_id: int, section_values: Structure) -> tuple[int, dict]:
        LOG.debug(f'Reading ini section {section_id}')
        code = self.lib.HJYFHR_ReadSectionIni(section_id, byref(section_values),
                                              sizeof(section_values))
        return code, _struct_to_dict(section_values)

    def read_firmware_ini(self) -> tuple:
        return self.read_section_ini(99, Firmware())

    def read_port_ini(self) -> tuple:
        return self.read_section_ini(100, Port())

    def read_spectrometer_ini(self) -> tuple:
        return self.read_section_ini(101, Spectrometer())

    def read_grating_ini(self, i: int) -> tuple:
        return self.read_section_ini(102 + i - 1, Grating())

    def read_slit_ini(self, i: int) -> tuple:
        return self.read_section_ini(112 + i - 1, Slit())

    def read_mirror_ini(self, i: int) -> tuple:
        return self.read_section_ini(116 + i - 1, DC())

    def read_shutter_ini(self) -> tuple:
        return self.read_section_ini(118, DC())

    def read_filter_ini(self) -> tuple:
        return self.read_section_ini(119, Filter())

    @check_error
    def create(self) -> tuple[int, None]:
        LOG.debug('Creating handle.')
        return self.lib.HJYFHR_Create(), None

    @check_error
    def delete(self) -> tuple[int, None]:
        LOG.debug('Deleting handle.')
        return self.lib.HJYFHR_Delete(), None

    @check_error
    def open_port(self, com_port: int, baudrate: int) -> tuple[int, None]:
        LOG.debug('Opening port.')
        return self.lib.HJYFHR_OpenPort(com_port, baudrate), None

    @check_error
    def close_port(self) -> tuple[int, None]:
        LOG.debug('Closing port.')
        return self.lib.HJYFHR_ClosePort(), None

    @check_error
    def set_baudrate(self, baudrate: int) -> tuple[int, None]:
        LOG.debug(f'Setting baudrate to {baudrate}.')
        return self.lib.HJYFHR_SetBaudRate(baudrate), None

    @check_error
    def set_port_timeout(self, timeout: int) -> tuple[int, None]:
        LOG.debug(f'Setting port timeout to {timeout}.')
        return self.lib.HJYFHR_SetPortTimeout(timeout), None

    @check_error
    def is_open_port(self) -> tuple[int, bool]:
        LOG.debug('Checking if port is open.')
        code = self.lib.HJYFHR_IsOpenPort(byref(is_open := c_int()))
        return code, bool(is_open)

    @check_error
    def set_setup(self, dispatcher: Dispatcher, setup: Structure) -> tuple[int, None]:
        LOG.debug(f'Setting up {dispatcher}.')
        return self.lib.HJYFHR_SetSetup(create_string_buffer(dispatcher.value.encode(), 30),
                                        byref(setup), sizeof(setup)), None

    def setup_motor(self, dispatcher: Dispatcher, motor: Spectrometer | Slit | Filter) -> int:
        # Grating & Slit & Filter
        setup_motor = SetupMotor(sizeof(SetupMotor),
                                 motor.SpeedMin,
                                 motor.SpeedMax,
                                 motor.Acceleration,
                                 motor.Backlash,
                                 motor.MotorStepUnit,
                                 motor.Reverse)
        return self.set_setup(dispatcher, setup_motor)

    def setup_grating(self, dispatcher: str, *fields: tuple) -> int:
        return self.setup_motor(Dispatcher(dispatcher), Spectrometer(*fields))

    def setup_slit(self, dispatcher: str, name: str, *fields: tuple) -> int:
        return self.setup_motor(Dispatcher(dispatcher), Slit(name.encode(), *fields))

    def setup_filter(self, dispatcher: str, name: str, *fields: tuple) -> int:
        return self.setup_motor(Dispatcher(dispatcher), Filter(name.encode(), *fields))

    def setup_dc(self, dispatcher: Dispatcher, dc: DC) -> int:
        # Mirror & Shutter
        setup_dc = SetupDC(sizeof(SetupDC),
                           dc.Delayms,
                           dc.DutyCyclePercent)
        return self.set_setup(dispatcher, setup_dc)

    def setup_mirror(self, dispatcher: str, name: str, *fields: tuple) -> int:
        return self.setup_dc(Dispatcher(dispatcher), DC(name.encode(), *fields))

    def setup_shutter(self, dispatcher: str, name: str, *fields: tuple) -> int:
        return self.setup_dc(Dispatcher(dispatcher), DC(name.encode(), *fields))

    @check_error
    def get_status(self, dispatcher: str) -> tuple[int, dict]:
        LOG.debug(f'Getting status of {dispatcher}.')
        code = self.lib.HJYFHR_GetStatus(create_string_buffer(dispatcher.encode(), 30),
                                         byref(status := Status()), sizeof(status))
        return code, _struct_to_dict(status)

    @check_error
    def initialization(self, dispatcher: str, init: Structure) -> tuple[int, None]:
        LOG.debug(f'Initializing {dispatcher}.')
        return self.lib.HJYFHR_Initialization(create_string_buffer(init.encode(), 30),
                                              byref(init), sizeof(init)), None

    # Motor functions
    @check_error
    def goto(self, dispatcher: str, position: int) -> tuple[int, int]:
        LOG.debug(f'Moving {dispatcher} to {position}.')
        self.get_status(dispatcher)
        code = self.lib.HJYFHR_Goto(create_string_buffer(dispatcher.encode(), 30),
                                    byref(position := c_int(position)), sizeof(c_int))
        return code, position.value

    @check_error
    def scan(self):
        ...

    @check_error
    def move_slit(self):
        ...

    @check_error
    def move_mirror(self, dispatcher: Dispatcher, position: int) -> tuple[int, None]:
        LOG.debug(f'Moving {dispatcher} to {position}.')
        self.get_status(dispatcher)
        code = self.lib.HJYFHR_MoveMirror(create_string_buffer(dispatcher.value.encode(), 30),
                                          byref(c_int(position)), sizeof(c_int))
        return code, None


def _struct_to_dict(struct: Structure) -> dict[str, Any]:
    return (
        {field: getattr(struct, field) for field, _ in struct._fields_}
        | {'__name__': struct.__class__.__name__}
    )
