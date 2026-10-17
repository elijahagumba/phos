"""ADR 0117's gate for the plant map (ADR 0142): its rule, its inputs and its one look."""

import hashlib
import json
from pathlib import Path

import pytest
from scripts.gate import (
    CANDIDATE,
    CORPORA,
    DECLARED_FILES,
    DECLARED_SHA256,
    OUT,
    PUBLISHED,
    declared_sha256,
    roles_for,
    verdict,
)

from phos.atlas.signal_roles import SignalRole

ROOT = Path(__file__).resolve().parents[2]


def row(champion: int, challenger: int, chance_max: int) -> dict[str, int]:
    return {"champion": champion, "challenger": challenger, "chance_max": chance_max}


def passing() -> dict[str, dict[str, int]]:
    return {
        "hai-21.03": row(42, 43, 8),
        "hai-22.04": row(53, 53, 9),
        "hai-23.05": row(36, 36, 8),
        "batadal": row(5, 5, 5),
    }


def test_more_on_one_hai_edition_and_no_fewer_anywhere_passes() -> None:
    assert verdict(passing()) == (True, [])


def test_one_fewer_anywhere_fails() -> None:
    rows = passing() | {"batadal": row(5, 4, 5)}
    passes, reasons = verdict(rows)
    assert not passes
    assert reasons == ["batadal: 4 is fewer than the champion's 5"]


def test_ties_everywhere_fail() -> None:
    rows = passing() | {"hai-21.03": row(42, 42, 8)}
    assert verdict(rows) == (
        False,
        ["no HAI edition where it catches strictly more than the champion"],
    )


def test_more_on_batadal_alone_is_not_more_on_a_hai_edition() -> None:
    rows = passing() | {"hai-21.03": row(42, 42, 8), "batadal": row(4, 5, 5)}
    assert not verdict(rows)[0]


def test_falling_to_chance_where_the_champion_is_above_it_fails() -> None:
    # Only reachable if the champion is itself near chance; the rule is checked on its own.
    rows = passing() | {"hai-23.05": row(9, 8, 8), "hai-22.04": row(9, 10, 9)}
    passes, reasons = verdict(rows)
    assert not passes
    assert "hai-23.05: 8 is not above every chance draw (8)" in reasons


def test_where_the_champion_is_at_chance_a_tie_at_chance_is_allowed() -> None:
    assert verdict(passing())[0]  # BATADAL: champion 5, chance max 5, challenger 5


def test_the_published_rows_are_the_a2_status_record() -> None:
    record = json.loads((ROOT / "eval_runs" / "v1" / "a2-status.json").read_text("utf-8"))
    published = {
        r["corpus"]: (r["consistency_caught"], r["attacks"], r["chance"]["max_caught"])
        for r in record["rows"]
        if r["corpus"] in CORPORA
    }
    assert published == PUBLISHED


def test_the_candidate_is_attempt_6_unchanged() -> None:
    assert json.loads(CANDIDATE.read_text("utf-8")) == {
        "detector": "atlas-plant-map-v1",
        "map": {"naming_rules": "adr-0135", "calibrator": "platt"},
    }


def test_a_corpus_without_a_role_file_gives_the_map_nothing(tmp_path: Path) -> None:
    roles = roles_for(tmp_path / "roles.toml", ("F_PU1", "L_T1"))
    assert roles.signals == ("F_PU1", "L_T1")
    assert roles.without_role() == ("F_PU1", "L_T1")


def test_batadal_has_no_role_file() -> None:
    assert not (ROOT / "data" / "batadal" / "roles.toml").exists()


def test_columns_the_reader_drops_are_dropped_from_the_roles() -> None:
    path = ROOT / "data" / "hai-22.04" / "roles.toml"
    roles = roles_for(path, ("P1_LIT01", "P1_LCV01D", "P1_B3004"))
    assert set(roles.signals) == {"P1_LIT01", "P1_LCV01D", "P1_B3004"}
    assert roles.role_of("P1_LIT01") is SignalRole.SENSOR
    kept = {s for loop in roles.loops for s in (loop.reading, loop.setpoint, *loop.outputs)}
    assert kept - {None} <= set(roles.signals)


def test_a_column_the_role_file_does_not_declare_stops_the_gate() -> None:
    with pytest.raises(SystemExit, match="does not declare"):
        roles_for(ROOT / "data" / "hai-22.04" / "roles.toml", ("P1_LIT01", "NOT_A_POINT"))


def test_the_gate_ran_once_and_failed_as_adr_0143_records() -> None:
    record = json.loads(OUT.read_text(encoding="utf-8"))
    assert record["passes"] is False
    assert record["declared_sha256"] == DECLARED_SHA256
    challenger = {name: row["challenger"] for name, row in record["corpora"].items()}
    assert challenger == {"hai-21.03": 40, "hai-22.04": 53, "hai-23.05": 35, "batadal": 5}
    adr = (ROOT / "docs" / "adr" / "0143-the-plant-map-fails-the-gate.md").read_text("utf-8")
    assert "**Verdict: fails ADR 0117 §3.3**" in adr


def test_the_gate_never_appends_the_log() -> None:
    script = (ROOT / "scripts" / "gate.py").read_text(encoding="utf-8")
    assert "append_to_experiment_log" not in script
    assert 'log.jsonl"' not in script


ADR_0142 = ROOT / "docs" / "adr" / "0142-the-plant-map-gate-is-declared.md"


def test_the_declared_files_are_the_ones_adr_0142_pins() -> None:
    assert declared_sha256() == DECLARED_SHA256
    assert f"`{DECLARED_SHA256}`" in ADR_0142.read_text(encoding="utf-8")


def test_adr_0142_pins_this_gate_script() -> None:
    script = hashlib.sha256((ROOT / "scripts" / "gate.py").read_bytes()).hexdigest()
    assert f"`scripts/gate.py` sha256 `{script}`" in ADR_0142.read_text(encoding="utf-8")


def test_every_role_file_the_challenger_reads_is_declared() -> None:
    for name in CORPORA:
        path = ROOT / "data" / name / "roles.toml"
        assert path.exists() == (f"data/{name}/roles.toml" in DECLARED_FILES)


def test_the_clean_editions_draw_chance_from_one_stream_in_their_published_order() -> None:
    from phos.eval import candidate_look, clean_hai

    assert clean_hai.CLEAN_CORPORA == candidate_look.CLEAN_CORPORA
    clean = tuple(c for c in CORPORA if c in clean_hai.CLEAN_CORPORA)
    assert clean == candidate_look.CLEAN_CORPORA
