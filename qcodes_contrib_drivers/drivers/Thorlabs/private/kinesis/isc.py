from __future__ import annotations

import pathlib
from functools import partial
from typing import Any, Mapping

from qcodes import validators as vals
from qcodes.parameters import Group, GroupParameter, Parameter
from . import enums
from .core import KinesisInstrument, ThorlabsKinesis


class KinesisISCInstrument(KinesisInstrument):
    """Devices which are controlled from the IntegratedStepperMotor dll.
    """

    def __init__(self, name: str, dll_dir: str | pathlib.Path | None = '',
                 serial: int | None = None, simulation: bool = False,
                 polling: int = 200, home: bool = False,
                 metadata: Mapping[Any, Any] | None = None,
                 label: str | None = None):
        super().__init__(name, dll_dir, serial, simulation, polling, home,
                         metadata, label)

        self.position = Parameter(
            "position",
            get_cmd=self._kinesis.get_position,
            set_cmd=self._kinesis.move_to_position,
            get_parser=partial(self._kinesis.real_value_from_device_unit,
                               unit_type=enums.ISCUnitType.Distance),
            set_parser=partial(self._kinesis.device_unit_from_real_value,
                               unit_type=enums.ISCUnitType.Distance),
            vals=vals.Numbers(0, 360),
            unit=u"\u00b0",
            label="Position",
            instrument=self
        )
        """The position in degrees. 
        
        Use :meth:`move_to_position` with argument block=True to block 
        execution until the targeted position is reached. You should 
        probably invalidate the parameter cache afterwards though.
        """

        # Would be nice to use Group and GroupParameter here, but
        # they're restricted to VISA commands...
        self.velocity = Parameter(
            "velocity",
            get_cmd=lambda: self._kinesis.get_vel_params()[0],
            set_cmd=lambda val: self._kinesis.set_vel_params(
                val, self.acceleration.get()
            ),
            get_parser=partial(self._kinesis.real_value_from_device_unit,
                               unit_type=enums.ISCUnitType.Velocity),
            set_parser=partial(self._kinesis.device_unit_from_real_value,
                               unit_type=enums.ISCUnitType.Velocity),
            unit=u"\u00b0/s",
            label="Velocity",
            instrument=self
        )
        self.acceleration = Parameter(
            "acceleration",
            get_cmd=lambda: self._kinesis.get_vel_params()[1],
            set_cmd=lambda val: self._kinesis.set_vel_params(
                self.acceleration.get(), val
            ),
            get_parser=partial(self._kinesis.real_value_from_device_unit,
                               unit_type=enums.ISCUnitType.Acceleration),
            set_parser=partial(self._kinesis.device_unit_from_real_value,
                               unit_type=enums.ISCUnitType.Acceleration),
            unit=u"\u00b0/s\u00b2",
            label="Acceleration",
            instrument=self
        )

    def _init_kinesis(self, dll_dir: str | pathlib.Path | None,
                      simulation: bool) -> ThorlabsKinesis:
        return ThorlabsKinesis(
            'Thorlabs.MotionControl.IntegratedStepperMotors.dll',
            self._prefix,
            dll_dir,
            simulation
        )
