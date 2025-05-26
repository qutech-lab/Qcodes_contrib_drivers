from __future__ import annotations

import ctypes
import enum
import os
import pathlib
import re
from collections import namedtuple
from pathlib import Path
from typing import Any

from qcodes.utils import DelayedKeyboardInterrupt

try:
    from msl.loadlib import Client64
except ImportError:
    raise ImportError('This driver requires the msl.loadlib package for '
                      'communicating with a 32-bit dll. You can install it '
                      "by running 'pip install msl.loadlib'")


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


class FHRClient(Client64):

    def __init__(self, dll_dir: str | os.PathLike | pathlib.Path,
                 filename: str = 'FHRCustomer'):
        module32 = str(Path(__file__).parent / 'fhr_server')
        super().__init__(module32=module32, dll_dir=dll_dir, filename=filename)

    def request32(self, name: str, *args, **kwargs) -> Any:
        with DelayedKeyboardInterrupt():
            return super().request32(name, *args, **kwargs)

    def read_firmware_ini(self) -> tuple:
        return _dict_to_namedtuple(self.request32('read_firmware_ini'))

    def read_port_ini(self) -> tuple:
        return _dict_to_namedtuple(self.request32('read_port_ini'))

    def read_spectrometer_ini(self) -> tuple:
        return _dict_to_namedtuple(self.request32('read_spectrometer_ini'))

    def read_grating_ini(self, i: int) -> tuple:
        return _dict_to_namedtuple(self.request32('read_grating_ini', i))

    def read_slit_ini(self, i: int) -> tuple:
        return _dict_to_namedtuple(self.request32('read_slit_ini', i))

    def read_mirror_ini(self, i: int) -> tuple:
        return _dict_to_namedtuple(self.request32('read_mirror_ini', i))

    def read_shutter_ini(self) -> tuple:
        return _dict_to_namedtuple(self.request32('read_shutter_ini'))

    def read_filter_ini(self) -> tuple:
        return _dict_to_namedtuple(self.request32('read_filter_ini'))

    def create(self):
        self.request32('create')

    def delete(self):
        self.request32('delete')

    def open_port(self, com_port: int, baudrate: int):
        self.request32('open_port', com_port, baudrate)

    def close_port(self):
        self.request32('close_port')

    def set_baudrate(self, baudrate: int):
        self.request32('set_baudrate', baudrate)

    def set_port_timeout(self, timeout: int):
        self.request32('set_port_timeout', timeout)

    def is_open_port(self) -> bool:
        return self.request32('is_open_port')

    def setup_grating(self, dispatcher: str, *fields: tuple):
        self.request32('setup_grating', dispatcher, *fields)

    def setup_slit(self, dispatcher: str, *fields: tuple):
        self.request32('setup_slit', dispatcher, *fields)

    def setup_filter(self, dispatcher: str, *fields: tuple):
        self.request32('setup_filter', dispatcher, *fields)

    def setup_mirror(self, dispatcher: str, *fields: tuple):
        self.request32('setup_mirror', dispatcher, *fields)

    def setup_shutter(self, dispatcher: str, *fields: tuple):
        self.request32('setup_shutter', dispatcher, *fields)

def _camel_to_snake(name: str) -> str:
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def _dict_to_namedtuple(dct: dict[str, Any]) -> namedtuple:
    cls = namedtuple(dct.pop('__name__'), [_camel_to_snake(key) for key in dct])
    return cls(*(val.decode() if isinstance(val, bytes) else val for val in dct.values()))
