"""Controller-source fixtures that stand in for the pinned ICSSim files.

These are **not** the pinned files. ADR 0370's declared score is the one run that
reads those, and this build does not run it, so the tests derive from text written
here instead. Each fixture reproduces the *shape* the derivation parses — the
statements and their order — not the formatting, because the derivation reads an
abstract syntax tree and formatting cannot reach it.

The one place the real files are read is the command ADR 0370 names.
"""

from __future__ import annotations

from typing import Final

#: `PLC1._logic`, with the same statements in the same order as the pinned file.
#: Wrapped differently only because this repository's line limit is 100 columns.
PLC1_TEXT: Final = """from ics_sim.Device import PLC
from Configs import TAG, Controllers, Connection


class PLC1(PLC):
    def _logic(self):
        if not self._check_manual_input(
            TAG.TAG_TANK_INPUT_VALVE_MODE, TAG.TAG_TANK_INPUT_VALVE_STATUS
        ):
            tank_level = self._get(TAG.TAG_TANK_LEVEL_VALUE)
            if tank_level > self._get(TAG.TAG_TANK_LEVEL_MAX):
                self._set(TAG.TAG_TANK_INPUT_VALVE_STATUS, 0)
            elif tank_level < self._get(TAG.TAG_TANK_LEVEL_MIN):
                self._set(TAG.TAG_TANK_INPUT_VALVE_STATUS, 1)

        if not self._check_manual_input(
            TAG.TAG_TANK_OUTPUT_VALVE_MODE, TAG.TAG_TANK_OUTPUT_VALVE_STATUS
        ):
            bottle_level = self._get(TAG.TAG_BOTTLE_LEVEL_VALUE)
            belt_position = self._get(TAG.TAG_BOTTLE_DISTANCE_TO_FILLER_VALUE)
            if bottle_level > self._get(TAG.TAG_BOTTLE_LEVEL_MAX) or belt_position > 1.0:
                self._set(TAG.TAG_TANK_OUTPUT_VALVE_STATUS, 0)
            else:
                self._set(TAG.TAG_TANK_OUTPUT_VALVE_STATUS, 1)
"""

#: `Configs.TAG`: the tag-name constants and the `TAG_LIST` table that holds each
#: tag's default. The release literal comes from this table, not from PLC1.
CONFIGS_TEXT: Final = """class TAG:
    TAG_TANK_INPUT_VALVE_STATUS = 'tank_input_valve_status'
    TAG_TANK_INPUT_VALVE_MODE = 'tank_input_valve_mode'

    TAG_TANK_LEVEL_VALUE = 'tank_level_value'
    TAG_TANK_LEVEL_MAX = 'tank_level_max'
    TAG_TANK_LEVEL_MIN = 'tank_level_min'

    TAG_TANK_OUTPUT_VALVE_STATUS = 'tank_output_valve_status'
    TAG_TANK_OUTPUT_VALVE_MODE = 'tank_output_valve_mode'

    TAG_BOTTLE_LEVEL_VALUE = 'bottle_level_value'
    TAG_BOTTLE_LEVEL_MAX = 'bottle_level_max'

    TAG_BOTTLE_DISTANCE_TO_FILLER_VALUE = 'bottle_distance_to_filler_value'

    TAG_LIST = {
        TAG_TANK_INPUT_VALVE_STATUS: {'id': 0, 'plc': 1, 'default': 1},
        TAG_TANK_INPUT_VALVE_MODE: {'id': 1, 'plc': 1, 'default': 3},
        TAG_TANK_LEVEL_VALUE: {'id': 2, 'plc': 1, 'default': 5.8},
        TAG_TANK_LEVEL_MIN: {'id': 3, 'plc': 1, 'default': 3},
        TAG_TANK_LEVEL_MAX: {'id': 4, 'plc': 1, 'default': 7},
        TAG_TANK_OUTPUT_VALVE_STATUS: {'id': 5, 'plc': 1, 'default': 0},
        TAG_TANK_OUTPUT_VALVE_MODE: {'id': 6, 'plc': 1, 'default': 3},
        TAG_BOTTLE_LEVEL_VALUE: {'id': 10, 'plc': 2, 'default': 0},
        TAG_BOTTLE_LEVEL_MAX: {'id': 11, 'plc': 2, 'default': 1.8},
        TAG_BOTTLE_DISTANCE_TO_FILLER_VALUE: {'id': 12, 'plc': 2, 'default': 0},
    }
"""

#: `Device.PLC._check_manual_input`: what a mode tag does. This is the only
#: statement of which modes are manual, and it names two of them.
DEVICE_TEXT: Final = """class PLC:
    def _check_manual_input(self, control_tag, actuator_tag):

        mode = self._get(control_tag)

        if mode == 1:
            self._set(actuator_tag, 0)
            return True
        elif mode == 2:
            self._set(actuator_tag, 1)
            return True
        return False
"""
