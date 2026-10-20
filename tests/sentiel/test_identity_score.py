"""Identity registers score what they name. The fixture is not CERT."""

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from phos.ontology import Domain, Entity, EntityType
from phos.sentiel.entities import EntityCatalogue, user_entity_id
from phos.sentiel.identity_score import (
    EMPTY_REGISTER_SHA256,
    directory_destination_register,
    score_traces,
    summarise_identity,
)
from phos.sentiel.named_counterparties import DeclaredIdentities, register_sha256
from phos.sentiel.traces import EntityDayTrace, write_traces


def _trace() -> EntityDayTrace:
    return EntityDayTrace(
        user_id="A",
        day=datetime(2010, 7, 1, tzinfo=UTC),
        hosts=("wikileaks.org",),
        recipients=("home@example.com",),
        pcs=("PC-1",),
    )


def test_an_empty_register_scores_zeros_on_named_counterparties() -> None:
    summary = summarise_identity(score_traces([_trace()], DeclaredIdentities()))
    assert summary["all_zero"] is True
    assert summary["register_sha256"] == EMPTY_REGISTER_SHA256
    features = summary["features"]
    assert isinstance(features, dict)
    for row in features.values():
        assert isinstance(row, dict)
        assert row["sum"] == 0.0
        assert row["max"] == 0.0


def test_a_declared_host_is_counted_when_the_register_names_it() -> None:
    register = DeclaredIdentities(hosts=frozenset({"wikileaks.org"}))
    summary = summarise_identity(score_traces([_trace()], register))
    features = summary["features"]
    assert isinstance(features, dict)
    hosts = features["declared_host_count"]
    assert isinstance(hosts, dict)
    assert hosts["sum"] == 1.0
    assert summary["register_sha256"] == register_sha256(register)
    assert summary["all_zero"] is False


def test_an_existing_identity_result_is_not_scored_again(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    out = tmp_path / "s2.json"
    out.write_text("{}\n", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "score_identity_features.py"),
            "--release",
            "r3.1",
            "--out",
            str(out),
            "--data-dir",
            str(tmp_path / "missing"),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert out.read_text(encoding="utf-8") == "{}\n"


def test_the_directory_register_names_email_addresses_and_nothing_else() -> None:
    stamp = datetime(2010, 1, 1, tzinfo=UTC)
    catalogue = EntityCatalogue(
        entities={
            "A": Entity(
                id=user_entity_id("A"),
                type=EntityType.USER,
                domain=Domain.SENTIEL,
                name="Ada",
                attributes={"email": "Ada@DTAA.com"},
                created_at=stamp,
            ),
            "B": Entity(
                id=user_entity_id("B"),
                type=EntityType.USER,
                domain=Domain.SENTIEL,
                name="Bea",
                attributes={},
                created_at=stamp,
            ),
        },
        directory_as_of=stamp,
        snapshots_read=1,
    )
    register = directory_destination_register(catalogue)
    assert register.destinations == frozenset({"ada@dtaa.com"})
    assert register.hosts == frozenset()
    assert register.pcs == frozenset()
    summary = summarise_identity(score_traces([_trace()], register))
    features = summary["features"]
    assert isinstance(features, dict)
    destinations = features["declared_destination_count"]
    hosts = features["declared_host_count"]
    assert isinstance(destinations, dict)
    assert isinstance(hosts, dict)
    assert destinations["sum"] == 0.0
    assert hosts["sum"] == 0.0
    assert summary["destinations_named"] == 0


def test_a_directory_address_is_named_when_the_day_mails_it() -> None:
    stamp = datetime(2010, 1, 1, tzinfo=UTC)
    catalogue = EntityCatalogue(
        entities={
            "A": Entity(
                id=user_entity_id("A"),
                type=EntityType.USER,
                domain=Domain.SENTIEL,
                name="Home",
                attributes={"email": "home@example.com"},
                created_at=stamp,
            )
        },
        directory_as_of=stamp,
        snapshots_read=1,
    )
    register = directory_destination_register(catalogue)
    summary = summarise_identity(score_traces([_trace()], register))
    features = summary["features"]
    assert isinstance(features, dict)
    destinations = features["declared_destination_count"]
    hosts = features["declared_host_count"]
    machines = features["declared_pc_count"]
    assert isinstance(destinations, dict)
    assert isinstance(hosts, dict)
    assert isinstance(machines, dict)
    assert destinations["sum"] == 1.0
    assert hosts["sum"] == 0.0
    assert machines["sum"] == 0.0
    assert summary["destinations_named"] == 1
    assert summary["all_zero"] is False


def test_the_script_scores_a_directory_register_without_writing_addresses(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    ldap = tmp_path / "r3.1" / "LDAP"
    ldap.mkdir(parents=True)
    (ldap / "2010-01.csv").write_text(
        "employee_name,user_id,email,role,business_unit,functional_unit,department,team,supervisor\n"
        "Ada,A,ada@dtaa.com,Sales,1,1,1,1,A\n",
        encoding="utf-8",
    )
    answers = tmp_path / "answers"
    answers.mkdir()
    (answers / "insiders.csv").write_text(
        "dataset,scenario,user,start,end\n3.1,1,A,01/02/2010 08:00:00,01/02/2010 17:00:00\n",
        encoding="utf-8",
    )
    cache = tmp_path / "traces.jsonl.gz"
    write_traces(
        [
            EntityDayTrace(
                user_id="A",
                day=datetime(2010, 7, 1, tzinfo=UTC),
                hosts=("wikileaks.org",),
                recipients=("ada@dtaa.com",),
                pcs=("PC-1",),
            )
        ],
        cache,
    )
    out = tmp_path / "s2.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "score_identity_features.py"),
            "--release",
            "r3.1",
            "--register",
            "directory",
            "--data-dir",
            str(tmp_path),
            "--cache",
            str(cache),
            "--out",
            str(out),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    text = out.read_text(encoding="utf-8")
    assert "ada@dtaa.com" not in text
    payload = json.loads(text)
    assert payload["register_source"] == "ldap-email"
    assert payload["register_counts"] == {"hosts": 0, "destinations": 1, "pcs": 0}
    assert payload["all_zero"] is False
    assert payload["destinations_named"] == 1
    assert payload["n_labelled_insiders"] == 1
    assert payload["weights_on_the_34"] is None
