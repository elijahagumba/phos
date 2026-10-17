#!/usr/bin/env python3
"""Write the role files of HAI 21.03, 22.04 and 23.05 from HAI 20.07's and the manual (ADR 0141).

HAI 20.07's role file (`data/hai-20.07/roles.toml`) was read row by row from the corpus authors'
manual at the registry's pin. The later editions share most of its points and add 28, all in the
same data-points table (pp. 12-15). This script writes each later edition's file from two
sources only:

1. **A point HAI 20.07 declares**, under the same column name or under the manual name the 20.07
   file records for it, keeps that declaration: its role, citation and quote.
2. **A point the table adds after 20.07** takes the role its own description states, by the 20.07
   file's reading rules, from `NEW_POINTS` below. Each entry quotes the manual verbatim.
3. **Any other column** gets no role, with the reason. A column the table does not name for that
   edition is never matched to a row by the shape of its name: HAI 23.05's ``x1001_15_ASSIGN_OUT``
   is not taken to be the HAIEnd table's ``1001.15-OUT``, and 21.03's ``P2_ASD`` not
   ``P2_AutoSD``.

The loops are 20.07's six, with each point renamed where the edition uses the manual's name and
dropped where the edition lacks it or gives it no role.

Usage::

    uv run python scripts/build_hai_roles.py    # data/hai-{21.03,22.04,23.05}/roles.toml
"""

from __future__ import annotations

import json
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
SOURCE: Final = ROOT / "data" / "hai-20.07" / "roles.toml"

#: Each edition's feature columns, as its first training file's header reads at the registry's pin
#: (time and label columns left out), fetched on 15 October 2026.
EDITIONS: Final[dict[str, tuple[str, ...]]] = {
    "hai-21.03": tuple(
        "P1_B2004 P1_B2016 P1_B3004 P1_B3005 P1_B4002 P1_B4005 P1_B400B P1_B4022 P1_FCV01D "
        "P1_FCV01Z P1_FCV02D P1_FCV02Z P1_FCV03D P1_FCV03Z P1_FT01 P1_FT01Z P1_FT02 P1_FT02Z "
        "P1_FT03 P1_FT03Z P1_LCV01D P1_LCV01Z P1_LIT01 P1_PCV01D P1_PCV01Z P1_PCV02D P1_PCV02Z "
        "P1_PIT01 P1_PIT02 P1_PP01AD P1_PP01AR P1_PP01BD P1_PP01BR P1_PP02D P1_PP02R P1_STSP "
        "P1_TIT01 P1_TIT02 P2_24Vdc P2_ASD P2_AutoGO P2_CO_rpm P2_Emerg P2_HILout P2_MSD "
        "P2_ManualGO P2_OnOff P2_RTR P2_SIT01 P2_SIT02 P2_TripEx P2_VT01 P2_VTR01 P2_VTR02 "
        "P2_VTR03 P2_VTR04 P2_VXT02 P2_VXT03 P2_VYT02 P2_VYT03 P3_FIT01 P3_LCP01D P3_LCV01D "
        "P3_LH P3_LIT01 P3_LL P3_PIT01 P4_HT_FD P4_HT_LD P4_HT_PO P4_HT_PS P4_LD P4_ST_FD "
        "P4_ST_GOV P4_ST_LD P4_ST_PO P4_ST_PS P4_ST_PT01 P4_ST_TT01".split()
    ),
    "hai-22.04": tuple(
        "P1_B2004 P1_B2016 P1_B3004 P1_B3005 P1_B4002 P1_B4005 P1_B400B P1_B4022 P1_FCV01D "
        "P1_FCV01Z P1_FCV02D P1_FCV02Z P1_FCV03D P1_FCV03Z P1_FT01 P1_FT01Z P1_FT02 P1_FT02Z "
        "P1_FT03 P1_FT03Z P1_LCV01D P1_LCV01Z P1_LIT01 P1_PCV01D P1_PCV01Z P1_PCV02D P1_PCV02Z "
        "P1_PIT01 P1_PIT01_HH P1_PIT02 P1_PP01AD P1_PP01AR P1_PP01BD P1_PP01BR P1_PP02D "
        "P1_PP02R P1_PP04 P1_PP04SP P1_SOL01D P1_SOL03D P1_STSP P1_TIT01 P1_TIT02 P1_TIT03 "
        "P2_24Vdc P2_ATSW_Lamp P2_AutoGO P2_AutoSD P2_Emerg P2_MASW P2_MASW_Lamp P2_ManualGO "
        "P2_ManualSD P2_OnOff P2_RTR P2_SCO P2_SCST P2_SIT01 P2_TripEx P2_VIBTR01 P2_VIBTR02 "
        "P2_VIBTR03 P2_VIBTR04 P2_VT01 P2_VTR01 P2_VTR02 P2_VTR03 P2_VTR04 P3_FIT01 P3_LCP01D "
        "P3_LCV01D P3_LH01 P3_LIT01 P3_LL01 P3_PIT01 P4_HT_FD P4_HT_PO P4_HT_PS P4_LD P4_ST_FD "
        "P4_ST_GOV P4_ST_LD P4_ST_PO P4_ST_PS P4_ST_PT01 P4_ST_TT01".split()
    ),
    "hai-23.05": tuple(
        "P1_FCV01D P1_FCV01Z P1_FCV02D P1_FCV02Z P1_FCV03D P1_FCV03Z P1_FT01 P1_FT01Z P1_FT02 "
        "P1_FT02Z P1_FT03 P1_FT03Z P1_LCV01D P1_LCV01Z P1_LIT01 P1_PCV01D P1_PCV01Z P1_PCV02D "
        "P1_PCV02Z P1_PIT01 P1_PIT01_HH P1_PIT02 P1_PP01AD P1_PP01AR P1_PP01BD P1_PP01BR "
        "P1_PP02D P1_PP02R P1_PP04 P1_PP04D P1_PP04SP P1_SOL01D P1_SOL03D P1_STSP P1_TIT01 "
        "P1_TIT02 P1_TIT03 P2_24Vdc P2_ATSW_Lamp P2_AutoGO P2_AutoSD P2_Emerg P2_MASW "
        "P2_MASW_Lamp P2_ManualGO P2_ManualSD P2_OnOff P2_RTR P2_SCO P2_SCST P2_SIT01 "
        "P2_TripEx P2_VIBTR01 P2_VIBTR02 P2_VIBTR03 P2_VIBTR04 P2_VT01 P2_VTR01 P2_VTR02 "
        "P2_VTR03 P2_VTR04 P3_FIT01 P3_LCP01D P3_LCV01D P3_LH01 P3_LIT01 P3_LL01 P3_PIT01 "
        "P4_HT_FD P4_HT_PO P4_HT_PS P4_LD P4_ST_FD P4_ST_GOV P4_ST_LD P4_ST_PO P4_ST_PS "
        "P4_ST_PT01 P4_ST_TT01 x1001_05_SETPOINT_OUT x1001_15_ASSIGN_OUT x1002_07_SETPOINT_OUT "
        "x1002_08_SETPOINT_OUT x1003_10_SETPOINT_OUT x1003_18_SETPOINT_OUT "
        "x1003_24_SUM_OUT".split()
    ),
}

#: The points the data-points table adds after 20.07: (role or None, row, printed page, the
#: manual's description verbatim, the reason when there is no role).
NEW_POINTS: Final[dict[str, tuple[str | None, int, int, str, str | None]]] = {
    "P1_PIT01_HH": (
        None,
        29,
        12,
        "Highest outlet pressure of the heat-exchanger",
        "The description does not say whether this is measured or a limit.",
    ),
    "P1_PP01AD": ("actuator", 31, 12, "Start command of the main water pump PP01A", None),
    "P1_PP01AR": ("actuator", 32, 12, "Running state of the main water pump PP01A", None),
    "P1_PP01BD": ("actuator", 33, 12, "Start command of the main water pump PP01B", None),
    "P1_PP01BR": ("actuator", 34, 12, "Running state of the main water pump PP01B", None),
    "P1_PP02D": ("actuator", 35, 12, "Start command of the heating water pump PP02", None),
    "P1_PP02R": ("actuator", 36, 12, "Running state of the heating water pump PP02", None),
    "P1_PP04": ("actuator", 37, 12, "Control out of the cooler pump", None),
    "P1_PP04SP": ("setpoint", 38, 12, "Cooler temperature setpoint", None),
    "P1_SOL01D": ("actuator", 39, 12, "Open command of the main water tank supply valve", None),
    "P1_SOL03D": ("actuator", 40, 12, "Open command of the main water tank drain valve", None),
    "P1_STSP": (
        None,
        41,
        13,
        "Start/stop command of the boiler DCS",
        "A start/stop command of the control system itself, not of a final control "
        "element: an operator switch, given no role as 20.07's buttons are.",
    ),
    "P1_TIT03": ("sensor", 44, 13, "Temperature of the main water tank", None),
    "P2_ATSW_Lamp": (None, 46, 13, "Lamp of the Auto SW", "An indicator lamp."),
    "P2_MASW": (None, 50, 13, "Manual(1)/Auto(0) SW", "An operator switch."),
    "P2_MASW_Lamp": (None, 51, 14, "Lamp of Manual SW", "An indicator lamp."),
    "P2_ManualGO": (None, 52, 14, "Manual start button", "An operator button."),
    "P2_ManualSD": ("setpoint", 53, 14, "Manual speed demand", None),
    "P2_RTR": (
        None,
        55,
        14,
        "RPM trip rate",
        "A trip rate: the description states neither a measurement nor a setpoint.",
    ),
    "P2_SCO": ("actuator", 56, 14, "Control output value of the speed controller", None),
    "P2_SCST": ("sensor", 57, 14, "Speed change proportional to frequency change of the STM", None),
    "P2_VTR01": (
        None,
        65,
        14,
        "Preset vibration limit for the sensor P2_VIBTR01",
        "A preset limit: not stated as a setpoint or demand, nor measured.",
    ),
    "P2_VTR02": (
        None,
        66,
        14,
        "Preset vibration limit for the sensor P2_VIBTR02",
        "A preset limit: not stated as a setpoint or demand, nor measured.",
    ),
    "P2_VTR03": (
        None,
        67,
        14,
        "Preset vibration limit for the sensor P2_VIBTR03",
        "A preset limit: not stated as a setpoint or demand, nor measured.",
    ),
    "P2_VTR04": (
        None,
        68,
        14,
        "Preset vibration limit for the sensor P2_VIBTR03",
        "A preset limit: not stated as a setpoint or demand, nor measured.",
    ),
    "P2_VT01": ("sensor", 64, 14, "Phase lag signal of the key phasor probe", None),
    "P3_LH01": ("setpoint", 72, 14, "High water level set-point", None),
    "P3_LL01": ("setpoint", 74, 14, "Low water level set-point", None),
    "P3_FIT01": ("sensor", 69, 14, "Flow rate of water flowing into the upper water tank", None),
    "P3_PIT01": ("sensor", 75, 14, "Pressure of water flowing into the upper water tank", None),
    "P4_ST_GOV": ("actuator", 82, 15, "Gate opening rate of STM", None),
}


def _string(value: str) -> str:
    return json.dumps(value)


def _declarations(source: Mapping[str, object]) -> tuple[dict[str, dict[str, object]], ...]:
    points = source["points"]
    assert isinstance(points, list)
    by_signal = {str(p["signal"]): p for p in points}
    by_manual = {str(p["manual_name"]): p for p in points if p.get("manual_name")}
    return by_signal, by_manual


def _point(
    column: str,
    edition: str,
    by_signal: Mapping[str, dict[str, object]],
    by_manual: Mapping[str, dict[str, object]],
) -> dict[str, object]:
    if column in by_signal or column in by_manual:
        same = by_signal.get(column)
        declared = dict(same if same is not None else by_manual[column])
        old = str(declared["signal"])
        declared["signal"] = column
        note = "HAI 20.07's role file" if old == column else f"HAI 20.07's role file (as {old})"
        declared["cited"] = f"{declared['cited']}; carried from {note}"
        if declared.get("manual_name") == column:
            declared.pop("manual_name")
        return declared
    if column in NEW_POINTS:
        role, row, page, quote, reason = NEW_POINTS[column]
        cited = f"Data points table, row {row} (p. {page})"
        if role is None:
            return {
                "signal": column,
                "role": "none",
                "cited": cited,
                "reason": f'{reason} Manual: "{quote}".',
            }
        return {"signal": column, "role": role, "cited": cited, "quote": quote}
    return {
        "signal": column,
        "role": "none",
        "cited": "Data points table (pp. 12-15)",
        "reason": f"The table does not name {column} for {edition.removeprefix('hai-')}; not "
        "inferred from the name.",
    }


def _loops(
    source: Mapping[str, object], points: Sequence[dict[str, object]]
) -> list[dict[str, object]]:
    roled = {str(p["signal"]) for p in points if p["role"] != "none"}
    rename = {
        str(p["cited"]).split("(as ")[-1].rstrip(")"): str(p["signal"])
        for p in points
        if "(as " in str(p["cited"])
    }
    out: list[dict[str, object]] = []
    raw_loops = source.get("loops", [])
    assert isinstance(raw_loops, list)
    for loop in raw_loops:

        def keep(name: object) -> str | None:
            mapped = rename.get(str(name), str(name))
            return mapped if mapped in roled else None

        reading = keep(loop["reading"]) if loop.get("reading") else None
        outputs = [o for o in (keep(x) for x in loop.get("outputs", [])) if o is not None]
        if reading is None and not outputs:
            continue
        if loop.get("reading") and reading is None:
            continue  # the loop's stated reading is missing; ADR 0126's fallback would not apply
        entry: dict[str, object] = {
            "name": loop["name"],
            "cited": loop["cited"],
            "statement": loop["statement"],
        }
        if reading is not None:
            entry["reading"] = reading
        if outputs:
            entry["outputs"] = outputs
        setpoint = keep(loop["setpoint"]) if loop.get("setpoint") else None
        if setpoint is not None:
            entry["setpoint"] = setpoint
        out.append(entry)
    return out


def render(edition: str, columns: Sequence[str], source: Mapping[str, object]) -> str:
    """One edition's role file as TOML text."""
    by_signal, by_manual = _declarations(source)
    points = [_point(c, edition, by_signal, by_manual) for c in columns]
    lines = [
        f"#  {edition.upper().replace('HAI-', 'HAI ')} — signal roles and loops "
        "(ADR 0123 §3, ADR 0126, ADR 0141)",
        "#",
        "#  Written by scripts/build_hai_roles.py from HAI 20.07's role file and the same manual,",
        "#  under its reading rules. Do not edit by hand: change the script and rerun it.",
        "",
        "schema_version = 1",
        f"corpus = {_string(edition)}",
        "",
        "[source]",
    ]
    src = source["source"]
    assert isinstance(src, dict)
    lines += [f"{key} = {_string(str(value))}" for key, value in src.items()]
    for point in points:
        lines += ["", "[[points]]"]
        for key in ("signal", "role", "cited", "quote", "manual_name", "loop", "reason"):
            if key in point and point[key] is not None:
                lines.append(f"{key} = {_string(str(point[key]))}")
    for loop in _loops(source, points):
        lines += ["", "[[loops]]"]
        for key in ("name", "cited", "statement", "reading", "setpoint"):
            if key in loop:
                lines.append(f"{key} = {_string(str(loop[key]))}")
        if "outputs" in loop:
            outputs = loop["outputs"]
            assert isinstance(outputs, list)
            lines.append("outputs = [" + ", ".join(_string(o) for o in outputs) + "]")
    return "\n".join(lines) + "\n"


def main() -> int:
    """Write every later edition's role file."""
    source = tomllib.loads(SOURCE.read_text(encoding="utf-8"))
    for edition, columns in EDITIONS.items():
        path = ROOT / "data" / edition / "roles.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(edition, columns, source), encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}: {len(columns)} points")
    return 0


if __name__ == "__main__":
    sys.exit(main())
