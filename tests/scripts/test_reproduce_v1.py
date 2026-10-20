"""The v1 reproduce checker (ADR 0221): a digit mismatch fails, payloads stay closed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts.reproduce_v1 import (
    PIN_RELATIVE,
    Check,
    PinnedRecord,
    canonical_digit,
    check_records,
    lookup,
    main,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "reproduce_v1.py"


def _pin(path: Path, digits: dict[str, str]) -> PinnedRecord:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    relative = "eval_runs/v1/row.json"
    return PinnedRecord(relative, digest, digits)


def test_a_matching_digit_is_record_intact(tmp_path: Path) -> None:
    record = tmp_path / "eval_runs" / "v1" / "row.json"
    record.parent.mkdir(parents=True)
    record.write_text('{"caught": 37}\n', encoding="utf-8")
    results = check_records(tmp_path, (_pin(record, {"caught": "37"}),))
    assert results == (
        Check("eval_runs/v1/row.json", "record intact", "sha256 ok; 1 digit matches"),
    )


def test_a_digit_mismatch_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    record = tmp_path / "eval_runs" / "v1" / "row.json"
    record.parent.mkdir(parents=True)
    record.write_text('{"caught": 36}\n', encoding="utf-8")
    pinned = _pin(record, {"caught": "37"})
    results = check_records(tmp_path, (pinned,))
    assert results[0].status == "fail"
    assert "recorded 36 != pinned 37" in results[0].detail
    pin_path = tmp_path / "pin.json"
    pin_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "records": [
                    {"path": pinned.path, "sha256": pinned.sha256, "digits": {"caught": "37"}}
                ],
            }
        ),
        encoding="utf-8",
    )
    code = main(["--root", str(tmp_path), "--pin", str(pin_path)])
    assert code == 1
    assert "fail" in capsys.readouterr().out


def test_a_checksum_mismatch_fails(tmp_path: Path) -> None:
    record = tmp_path / "eval_runs" / "v1" / "row.json"
    record.parent.mkdir(parents=True)
    record.write_text('{"caught": 37}\n', encoding="utf-8")
    pinned = PinnedRecord("eval_runs/v1/row.json", "a" * 64, {"caught": "37"})
    results = check_records(tmp_path, (pinned,))
    assert results[0].status == "fail"
    assert "sha256" in results[0].detail


def test_validation_paths_are_refused_without_being_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "data" / "batadal" / "score.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"caught": 5}\n', encoding="utf-8")
    opened: list[Path] = []
    original = Path.read_bytes

    def spy(self: Path) -> bytes:
        opened.append(self)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", spy)
    results = check_records(
        tmp_path,
        (PinnedRecord("data/batadal/score.json", "b" * 64, {"caught": "5"}),),
    )
    assert results[0].status == "fail"
    assert results[0].detail == "refused: validation corpus is not opened"
    assert opened == []


def test_lookup_selects_a_row_and_canonicalises() -> None:
    payload = {
        "rows": [
            {"corpus": "hai-20.07", "caught": 37},
            {"corpus": "hai-21.03", "caught": 42},
        ]
    }
    assert lookup(payload, "rows[corpus=hai-21.03].caught") == 42
    chained = {
        "rows": [
            {"dataset": "hai", "detector": "other", "fp_per_normal_hour": 1.0},
            {"dataset": "hai", "detector": "atlas-mahalanobis", "fp_per_normal_hour": 646.58},
        ]
    }
    assert lookup(chained, "rows[dataset=hai][detector=atlas-mahalanobis].fp_per_normal_hour") == (
        646.58
    )
    assert canonical_digit(0.104) == "0.104"
    assert canonical_digit(646.58) == "646.58"


def test_script_does_not_name_the_evaluation_log() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "log.jsonl" not in text
    assert "write_text" not in text
    assert "open(" not in text


def test_committed_pin_matches_the_checkout(capsys: pytest.CaptureFixture[str]) -> None:
    pin = json.loads((ROOT / PIN_RELATIVE).read_text(encoding="utf-8"))
    for item in pin["records"]:
        path = str(item["path"])
        assert path.startswith("eval_runs/")
        assert not path.startswith("data/")
    log = ROOT / "eval_runs" / "log.jsonl"
    before = log.stat().st_mtime_ns if log.exists() else None
    code = main(["--root", str(ROOT), "--check-only"])
    after = log.stat().st_mtime_ns if log.exists() else None
    printed = capsys.readouterr().out
    assert code == 0
    assert before == after
    assert "record intact" in printed
    assert "\nfail\t" not in printed
