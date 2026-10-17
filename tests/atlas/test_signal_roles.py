"""Declared signal roles (ADR 0123 §3): the loader's refusals, and the committed HAI 20.07 file.

The fixture tests prove the machinery and pass on a fresh clone. The HAI tests check the committed
`data/hai-20.07/roles.toml` against what it claims: one declaration per HAI 20.07 column, every
role cited to the pinned manual, and the columns the manual does not describe left without one.
The header comparison needs the git-ignored corpus and skips cleanly without it.
"""

import gzip
from pathlib import Path

import pytest

from phos.atlas.signal_roles import (
    SCHEMA_VERSION,
    ControlLoop,
    RoleDeclaration,
    RoleError,
    SignalRole,
    SignalRoles,
    load_roles,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
HAI_2007 = DATA_DIR / "hai-20.07"
ROLES_PATH = HAI_2007 / "roles.toml"
HAI_PIN = "2a814cebc9a66b06c9e5cd545e2d72e65d383737"
MANUAL_SHA256 = "0668345c4e80331b918fe17c81f8f363b13bd22886831d286e761bc62b71a556"
LABEL_COLUMNS = frozenset({"time", "attack", "attack_P1", "attack_P2", "attack_P3"})

#: The 59 SCADA columns of HAI 20.07, in file order, as its four CSV headers read on 13 October.
HAI_2007_COLUMNS = (
    "P1_B2004 P1_B2016 P1_B3004 P1_B3005 P1_B4002 P1_B4005 P1_B400B P1_B4022 P1_FCV01D "
    "P1_FCV01Z P1_FCV02D P1_FCV02Z P1_FCV03D P1_FCV03Z P1_FT01 P1_FT01Z P1_FT02 P1_FT02Z "
    "P1_FT03 P1_FT03Z P1_LCV01D P1_LCV01Z P1_LIT01 P1_PCV01D P1_PCV01Z P1_PCV02D P1_PCV02Z "
    "P1_PIT01 P1_PIT02 P1_TIT01 P1_TIT02 P2_24Vdc P2_Auto P2_Emgy P2_On P2_SD01 P2_SIT01 "
    "P2_TripEx P2_VT01e P2_VXT02 P2_VXT03 P2_VYT02 P2_VYT03 P3_LCP01D P3_LCV01D P3_LH P3_LL "
    "P3_LT01 P4_HT_FD P4_HT_LD P4_HT_PO P4_HT_PS P4_LD P4_ST_FD P4_ST_LD P4_ST_PO P4_ST_PS "
    "P4_ST_PT01 P4_ST_TT01"
).split()


def _declared(signal: str, role: SignalRole | None, **fields: str) -> RoleDeclaration:
    if role is None:
        return RoleDeclaration(signal=signal, role=None, cited="p. 1", reason="not described")
    return RoleDeclaration(signal=signal, role=role, cited="p. 1", quote=f"{signal} quoted")


def _fixture(tmp_path: Path, body: str, version: int = SCHEMA_VERSION) -> Path:
    path = tmp_path / "roles.toml"
    path.write_text(
        f"schema_version = {version}\n"
        'corpus = "fixture"\n'
        "[source]\n"
        'document = "A manual"\n'
        'repository = "example/plant"\n'
        'pin = "abc123"\n'
        'sha256 = "00ff"\n' + body,
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------- machinery


def test_roles_answer_by_signal_and_by_role() -> None:
    roles = SignalRoles(
        [
            _declared("level", SignalRole.SENSOR),
            _declared("valve", SignalRole.ACTUATOR),
            _declared("target", SignalRole.SETPOINT),
            _declared("button", None),
        ],
        ["level", "valve", "target", "button"],
        source="fixture",
    )
    assert roles.role_of("level") is SignalRole.SENSOR
    assert roles.role_of("button") is None
    assert roles.with_role(SignalRole.SETPOINT) == ("target",)
    assert roles.without_role() == ("button",)
    assert roles.signals == ("level", "valve", "target", "button")


def test_a_role_needs_a_quote_and_no_role_needs_a_reason() -> None:
    with pytest.raises(ValueError, match="quote"):
        RoleDeclaration(signal="x", role=SignalRole.SENSOR, cited="p. 1")
    with pytest.raises(ValueError, match="reason"):
        RoleDeclaration(signal="x", role=None, cited="p. 1")
    with pytest.raises(ValueError, match="cited"):
        RoleDeclaration(signal="x", role=SignalRole.SENSOR, cited="  ", quote="q")


@pytest.mark.parametrize(
    ("declared", "corpus", "message"),
    [
        (["a", "a"], ["a"], "twice"),
        (["a", "b"], ["a"], "not in the corpus"),
        (["a"], ["a", "b"], "no declaration"),
    ],
)
def test_a_partial_or_padded_declaration_is_refused(
    declared: list[str], corpus: list[str], message: str
) -> None:
    with pytest.raises(RoleError, match=message):
        SignalRoles([_declared(s, SignalRole.SENSOR) for s in declared], corpus, source="x")


def test_the_loader_reads_a_file_and_refuses_another_version(tmp_path: Path) -> None:
    body = (
        '[[points]]\nsignal = "a"\nrole = "sensor"\ncited = "p. 2"\nquote = "Level"\n'
        '[[points]]\nsignal = "b"\nrole = "none"\ncited = "p. 2"\nreason = "A button"\n'
    )
    roles = load_roles(_fixture(tmp_path, body), ["a", "b"])
    assert roles.role_of("a") is SignalRole.SENSOR
    assert roles.role_of("b") is None
    assert "example/plant" in roles.source and "abc123" in roles.source
    with pytest.raises(RoleError, match="schema_version"):
        load_roles(_fixture(tmp_path, body, version=SCHEMA_VERSION + 1), ["a", "b"])


def test_the_loader_refuses_an_unknown_role_and_a_missing_source_field(tmp_path: Path) -> None:
    bad_role = '[[points]]\nsignal = "a"\nrole = "controller"\ncited = "p. 2"\nquote = "q"\n'
    with pytest.raises(RoleError, match="controller"):
        load_roles(_fixture(tmp_path, bad_role), ["a"])
    path = tmp_path / "nosource.toml"
    path.write_text(
        f'schema_version = {SCHEMA_VERSION}\ncorpus = "x"\n[source]\ndocument = "d"\n'
        '[[points]]\nsignal = "a"\nrole = "sensor"\ncited = "p"\nquote = "q"\n',
        encoding="utf-8",
    )
    with pytest.raises(RoleError, match="pin"):
        load_roles(path, ["a"])


# ---------------------------------------------------------------------------- HAI 20.07


def _hai() -> SignalRoles:
    return load_roles(ROLES_PATH, HAI_2007_COLUMNS)


def _loop(**fields: object) -> ControlLoop:
    return ControlLoop.model_validate({"name": "L", "cited": "p. 1", "statement": "s", **fields})


def test_a_loop_must_name_signals_in_their_declared_roles() -> None:
    declared = [
        _declared("level", SignalRole.SENSOR),
        _declared("valve", SignalRole.ACTUATOR),
        _declared("target", SignalRole.SETPOINT),
    ]
    keys = ("level", "valve", "target")
    good = _loop(reading="level", outputs=("valve",), setpoint="target")
    assert SignalRoles(declared, keys, source="m", loops=[good]).loops == (good,)
    for bad in (
        _loop(reading="valve", outputs=("valve",)),
        _loop(reading="level", outputs=("level",)),
        _loop(reading="level", setpoint="valve"),
        _loop(reading="ghost"),
    ):
        with pytest.raises(RoleError):
            SignalRoles(declared, keys, source="m", loops=[bad])
    with pytest.raises(ValueError, match="neither a reading nor an output"):
        _loop()


def test_the_loader_reads_declared_loops(tmp_path: Path) -> None:
    path = _fixture(
        tmp_path,
        '[[points]]\nsignal = "a"\nrole = "sensor"\ncited = "p. 1"\nquote = "A"\n'
        '[[points]]\nsignal = "b"\nrole = "actuator"\ncited = "p. 1"\nquote = "B"\n'
        '[[loops]]\nname = "AC"\ncited = "p. 2"\nstatement = "b holds a"\n'
        'reading = "a"\noutputs = ["b"]\n',
    )
    (loop,) = load_roles(path, ("a", "b")).loops
    assert (loop.reading, loop.outputs) == ("a", ("b",))
    bad = _fixture(tmp_path, '[[loops]]\nname = "X"\ncited = "p. 2"\nstatement = "s"\n')
    with pytest.raises(RoleError):
        load_roles(bad, ())


def test_hai_loops_are_the_manual_s_loop_statements() -> None:
    roles = _hai()
    stated = {d.loop for d in roles.declarations if d.loop}
    assert {loop.name for loop in roles.loops} == {s.split(" ")[0] for s in stated}
    for loop in roles.loops:
        (line,) = [s for s in stated if s.startswith(f"{loop.name} ")]
        assert loop.statement in line
        assert loop.cited.endswith(line[line.index("(") : line.index(")") + 1])
    by_name = {loop.name: loop for loop in roles.loops}
    assert by_name["P1-LC"].reading == "P1_LIT01"
    assert by_name["P1-LC"].outputs == ("P1_LCV01D",)
    assert by_name["P2-SC"].outputs == ()  # the statement names no output
    assert by_name["P3-LC"].reading is None  # nor this one a reading


def test_hai_roles_cover_every_column_once_and_cite_the_pinned_manual() -> None:
    roles = _hai()
    assert roles.signals == tuple(HAI_2007_COLUMNS)
    assert len(roles.signals) == 59  # the manual's own total for 20.07 (p. 15)
    assert HAI_PIN in roles.source
    assert MANUAL_SHA256 in roles.source
    for declaration in roles.declarations:
        assert declaration.cited.strip()
        if declaration.role is not None:
            assert "p. " in declaration.cited


def test_hai_loop_points_take_the_roles_the_manual_states() -> None:
    roles = _hai()
    # P1-LC (p. 7): LCV01D holds LIT01 at the operator's setpoint command B3004.
    assert roles.role_of("P1_LIT01") is SignalRole.SENSOR
    assert roles.role_of("P1_B3004") is SignalRole.SETPOINT
    assert roles.role_of("P1_LCV01D") is SignalRole.ACTUATOR
    # P2-SC (p. 10): SIT01 held at AutoSD, which 20.07 names SD01 (p. 13).
    assert roles.role_of("P2_SIT01") is SignalRole.SENSOR
    assert roles.role_of("P2_SD01") is SignalRole.SETPOINT


def test_hai_columns_the_manual_does_not_name_for_20_07_have_no_role() -> None:
    roles = _hai()
    unnamed = {"P2_VT01e", "P3_LH", "P3_LL"}
    buttons = {"P2_Auto", "P2_Emgy", "P2_On", "P2_TripEx"}
    assert set(roles.without_role()) == unnamed | buttons
    for signal in unnamed:
        (declaration,) = [d for d in roles.declarations if d.signal == signal]
        assert declaration.reason is not None and "not inferred" in declaration.reason


@pytest.mark.skipif(not (HAI_2007 / "train1.csv.gz").is_file(), reason="HAI 20.07 not on disk")
@pytest.mark.parametrize("name", ["train1", "train2", "test1", "test2"])
def test_hai_role_file_matches_each_corpus_header(name: str) -> None:
    with gzip.open(HAI_2007 / f"{name}.csv.gz", "rt", encoding="utf-8") as handle:
        header = handle.readline().strip().replace(";", ",").split(",")
    signals = [column for column in header if column and column not in LABEL_COLUMNS]
    assert signals == list(HAI_2007_COLUMNS)
