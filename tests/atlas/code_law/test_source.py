"""Reading the pinned controller source: digests checked, nothing imported."""

from __future__ import annotations

import hashlib
from pathlib import Path

from tests.atlas.code_law.fixtures import CONFIGS_TEXT, DEVICE_TEXT, PLC1_TEXT

from phos.atlas.code_law import (
    DECLARED_SOURCES,
    RefusalReason,
    pinned_source_from_text,
    read_pinned_source,
)


def _write(root: Path, texts: dict[str, str]) -> None:
    for relative, text in texts.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def _declared_digests() -> dict[str, str]:
    return {source.relative: source.sha256 for source in DECLARED_SOURCES}


def test_three_files_are_declared_and_no_others() -> None:
    assert [source.relative for source in DECLARED_SOURCES] == [
        "src/PLC1.py",
        "src/Configs.py",
        "src/ics_sim/Device.py",
    ]


def test_each_declared_digest_is_a_sha256() -> None:
    for source in DECLARED_SOURCES:
        assert len(source.sha256) == 64
        assert set(source.sha256) <= set("0123456789abcdef")


def test_a_file_whose_digest_does_not_match_is_refused(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "src/PLC1.py": PLC1_TEXT,
            "src/Configs.py": CONFIGS_TEXT,
            "src/ics_sim/Device.py": DEVICE_TEXT,
        },
    )
    read = read_pinned_source(tmp_path)
    assert read.source is None
    assert len(read.refusals) == 3
    for refusal in read.refusals:
        assert refusal.reason is RefusalReason.DIGEST_MISMATCH
        assert refusal.expected == _declared_digests()[refusal.relative]
        assert refusal.found != refusal.expected


def test_an_absent_file_is_refused_and_does_not_raise(tmp_path: Path) -> None:
    read = read_pinned_source(tmp_path)
    assert read.source is None
    assert {refusal.reason for refusal in read.refusals} == {RefusalReason.FILE_ABSENT}
    assert {refusal.relative for refusal in read.refusals} == set(_declared_digests())


def test_a_matching_tree_is_read_with_its_digests(tmp_path: Path) -> None:
    texts = {
        "src/PLC1.py": PLC1_TEXT,
        "src/Configs.py": CONFIGS_TEXT,
        "src/ics_sim/Device.py": DEVICE_TEXT,
    }
    _write(tmp_path, texts)
    # Stand the fixtures in for the pinned bytes by declaring their own digests.
    overrides = tuple(
        (relative, hashlib.sha256(text.encode("utf-8")).hexdigest())
        for relative, text in texts.items()
    )
    read = read_pinned_source(tmp_path, digests=dict(overrides))
    assert read.refusals == ()
    assert read.source is not None
    assert read.source.plc1.text == PLC1_TEXT
    assert read.source.configs.relative == "src/Configs.py"
    assert read.source.device.sha256 == dict(overrides)["src/ics_sim/Device.py"]


def test_from_text_computes_its_own_digests() -> None:
    source = pinned_source_from_text(plc1=PLC1_TEXT, configs=CONFIGS_TEXT, device=DEVICE_TEXT)
    assert source.plc1.sha256 == hashlib.sha256(PLC1_TEXT.encode("utf-8")).hexdigest()
    assert source.device.text == DEVICE_TEXT


def test_the_reader_never_imports_or_executes_the_source(tmp_path: Path) -> None:
    # A file that would raise the moment it ran, and would register a module if
    # imported. Reading it as text must do neither.
    poison = "raise SystemExit('the source was executed')\n"
    _write(
        tmp_path,
        {
            "src/PLC1.py": poison,
            "src/Configs.py": poison,
            "src/ics_sim/Device.py": poison,
        },
    )
    digest = hashlib.sha256(poison.encode("utf-8")).hexdigest()
    read = read_pinned_source(
        tmp_path,
        digests={source.relative: digest for source in DECLARED_SOURCES},
    )
    assert read.refusals == ()
    assert read.source is not None
    assert read.source.plc1.text == poison
