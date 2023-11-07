from __future__ import annotations

import pathlib
from functools import partial
from typing import Any, Mapping

from qcodes import validators as vals
from qcodes.parameters import Parameter
from . import enums
from .core import KinesisInstrument, ThorlabsKinesis, to_enum


class KinesisCCInstrument(KinesisInstrument):
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
            unit=u"\u00b0",
            label="Position",
            instrument=self
        )
        """The position in degrees. 

        Note:
            Use :meth:`move_to_position` with argument block=True to 
            block execution until the targeted position is reached. You 
            should probably invalidate the parameter cache afterwards.
        """

        # Would be nice to use Group and GroupParameter here, but
        # they're restricted to VISA commands...
        self.velocity = Parameter(
            "velocity",
            get_cmd=lambda: self._kinesis.get_vel_params()[0],
            set_cmd=lambda val: self._kinesis.set_vel_params(
                val, self.acceleration.get()
            ),
            unit=u"\u00b0/s",
            label="Velocity",
            instrument=self
        )
        """The velocity in degrees per second."""
        self.acceleration = Parameter(
            "acceleration",
            get_cmd=lambda: self._kinesis.get_vel_params()[1],
            set_cmd=lambda val: self._kinesis.set_vel_params(
                self.acceleration.get(), val
            ),
            unit=u"\u00b0/s\u00b2",
            label="Acceleration",
            instrument=self
        )
        """The acceleration in degrees per square second."""

        self.jog_mode = Parameter(
            "jog_mode",
            get_cmd=lambda: self._kinesis.get_jog_mode()[0],
            set_cmd=lambda val: self._kinesis.set_jog_mode(
                val, self._kinesis.get_jog_mode()[1]
            ),
            set_parser=to_enum,
            label="Jog mode",
            instrument=self
        )
        self.stop_mode = Parameter(
            "stop_mode",
            get_cmd=lambda: self._kinesis.get_jog_mode()[1],
            set_cmd=lambda val: self._kinesis.set_jog_mode(
                self._kinesis.get_jog_mode()[0], val
            ),
            set_parser=to_enum,
            label="Stop mode",
            instrument=self
        )

    def _init_kinesis(self, dll_dir: str | pathlib.Path | None,
                      simulation: bool) -> ThorlabsKinesis:
        return ThorlabsKinesis(
            'Thorlabs.MotionControl.KCube.DCServo.dll',
            self._prefix,
            dll_dir,
            simulation
        )
