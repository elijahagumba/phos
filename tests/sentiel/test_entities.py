"""Tests for the LDAP entity catalogue and the derived, reversible entity ids."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from phos.ontology import Domain, EntityType
from phos.sentiel import (
    ABSENT_FROM_DIRECTORY,
    DIRECTORY_RECORD_ATTRIBUTE,
    CertFormatError,
    EntityCatalogue,
    user_entity_id,
    user_id_of,
)

SECOND_SNAPSHOT = (
    "employee_name,user_id,email,role,business_unit,functional_unit,"
    "department,team,supervisor\n"
    "Alice A One,ALICE001,alice.a.one@dtaa.com,SalesManager,1,2 - Sales,"
    "3 - Retail,Team B,New Boss\n"
)


def test_user_entity_id_is_derived_and_reversible() -> None:
    assert user_entity_id("CSF0929") == "ent_CSF0929"
    assert user_id_of("ent_CSF0929") == "CSF0929"


def test_user_entity_id_is_stable_across_calls() -> None:
    """Derived, not minted: two runs over one corpus must produce identical ids (§3.7)."""
    assert user_entity_id("CSF0929") == user_entity_id("CSF0929")


def test_user_id_of_passes_a_bare_user_id_through() -> None:
    assert user_id_of("CSF0929") == "CSF0929"


def test_catalogue_maps_users_to_role_team_and_department(release_dir: Path) -> None:
    catalogue = EntityCatalogue.from_ldap_directory(release_dir / "LDAP")

    alice = catalogue.entities["ALICE001"]
    assert alice.id == "ent_ALICE001"
    assert alice.type is EntityType.USER
    assert alice.domain is Domain.SENTIEL
    assert alice.name == "Alice A One"
    assert alice.attributes["role"] == "Salesman"
    assert alice.attributes["team"] == "Team A"
    assert alice.attributes["department"] == "3 - Retail"
    assert alice.attributes["functional_unit"] == "2 - Sales"
    assert alice.attributes["supervisor"] == "Boss Person"
    assert alice.attributes[DIRECTORY_RECORD_ATTRIBUTE] == "present"


def test_catalogue_omits_an_empty_directory_cell(release_dir: Path) -> None:
    """Mallory's `team` is blank in the fixture; an absent fact is absent, not an empty string."""
    mallory = EntityCatalogue.from_ldap_directory(release_dir / "LDAP").entities["MALLORY9"]
    assert "team" not in mallory.attributes
    assert mallory.attributes["role"] == "ITAdmin"


def test_catalogue_records_when_the_directory_was_read(release_dir: Path) -> None:
    catalogue = EntityCatalogue.from_ldap_directory(release_dir / "LDAP")
    assert catalogue.directory_as_of == datetime(2010, 1, 1, tzinfo=UTC)
    assert catalogue.snapshots_read == 1


def test_later_snapshots_win(release_dir: Path) -> None:
    """People change teams; the catalogue describes the organisation as it ended up."""
    (release_dir / "LDAP" / "2010-06.csv").write_text(SECOND_SNAPSHOT, encoding="utf-8")
    catalogue = EntityCatalogue.from_ldap_directory(release_dir / "LDAP")

    assert catalogue.entities["ALICE001"].attributes["role"] == "SalesManager"
    assert catalogue.entities["ALICE001"].attributes["team"] == "Team B"
    assert catalogue.directory_as_of == datetime(2010, 6, 1, tzinfo=UTC)
    assert catalogue.snapshots_read == 2


def test_a_user_who_left_is_still_catalogued(release_dir: Path) -> None:
    """The merge is a union: a user in an early snapshot only is kept, never quietly deleted."""
    (release_dir / "LDAP" / "2010-06.csv").write_text(SECOND_SNAPSHOT, encoding="utf-8")
    catalogue = EntityCatalogue.from_ldap_directory(release_dir / "LDAP")
    assert "MALLORY9" in catalogue.entities


def test_a_user_absent_from_the_directory_is_synthesised_not_dropped(release_dir: Path) -> None:
    """The documented policy, asserted: never silently dropped."""
    catalogue = EntityCatalogue.from_ldap_directory(release_dir / "LDAP")

    ghost = catalogue.entity_for("NOBODY01")

    assert ghost.id == "ent_NOBODY01"
    assert ghost.type is EntityType.USER
    assert ghost.domain is Domain.SENTIEL
    assert ghost.attributes[DIRECTORY_RECORD_ATTRIBUTE] == ABSENT_FROM_DIRECTORY
    assert "role" not in ghost.attributes


def test_absent_user_ids_reports_the_gap(release_dir: Path) -> None:
    catalogue = EntityCatalogue.from_ldap_directory(release_dir / "LDAP")
    assert catalogue.absent_user_ids(frozenset({"ALICE001", "NOBODY01"})) == frozenset({"NOBODY01"})


def test_entity_for_returns_the_catalogued_entity_when_known(release_dir: Path) -> None:
    catalogue = EntityCatalogue.from_ldap_directory(release_dir / "LDAP")
    assert catalogue.entity_for("ALICE001") is catalogue.entities["ALICE001"]


def test_email_domains_are_read_off_the_corpus(release_dir: Path) -> None:
    catalogue = EntityCatalogue.from_ldap_directory(release_dir / "LDAP")
    assert catalogue.email_domains() == {"dtaa.com": 2}
    assert catalogue.dominant_email_domain() == "dtaa.com"


def test_dominant_email_domain_is_empty_when_nothing_has_one(tmp_path: Path) -> None:
    ldap = tmp_path / "LDAP"
    ldap.mkdir()
    (ldap / "2010-01.csv").write_text("user_id\nALICE001\n", encoding="utf-8")
    assert EntityCatalogue.from_ldap_directory(ldap).dominant_email_domain() == ""


def test_a_snapshot_missing_user_id_raises(tmp_path: Path) -> None:
    ldap = tmp_path / "LDAP"
    ldap.mkdir()
    (ldap / "2010-01.csv").write_text("employee_name,email\nA,a@b.com\n", encoding="utf-8")
    with pytest.raises(CertFormatError, match="missing required column"):
        EntityCatalogue.from_ldap_directory(ldap)


def test_a_snapshot_with_an_unknown_column_raises(tmp_path: Path) -> None:
    ldap = tmp_path / "LDAP"
    ldap.mkdir()
    (ldap / "2010-01.csv").write_text("user_id,clearance\nA,secret\n", encoding="utf-8")
    with pytest.raises(CertFormatError, match="unrecognised column"):
        EntityCatalogue.from_ldap_directory(ldap)


def test_a_blank_user_id_row_is_skipped(tmp_path: Path) -> None:
    ldap = tmp_path / "LDAP"
    ldap.mkdir()
    (ldap / "2010-01.csv").write_text("user_id,role\n,Nobody\nA,Someone\n", encoding="utf-8")
    assert set(EntityCatalogue.from_ldap_directory(ldap).entities) == {"A"}


def test_a_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(CertFormatError, match="LDAP directory not found"):
        EntityCatalogue.from_ldap_directory(tmp_path / "nope")


def test_an_empty_directory_raises(tmp_path: Path) -> None:
    empty = tmp_path / "LDAP"
    empty.mkdir()
    with pytest.raises(CertFormatError, match="no LDAP snapshots"):
        EntityCatalogue.from_ldap_directory(empty)


def test_a_snapshot_not_named_as_a_month_is_read_but_stamped_at_the_epoch(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ldap = tmp_path / "LDAP"
    ldap.mkdir()
    (ldap / "directory.csv").write_text("user_id,role\nA,Someone\n", encoding="utf-8")
    with caplog.at_level("WARNING", logger="phos.sentiel.entities"):
        catalogue = EntityCatalogue.from_ldap_directory(ldap)

    assert catalogue.entities["A"].created_at == datetime(1970, 1, 1, tzinfo=UTC)
    assert any("not named YYYY-MM" in record.getMessage() for record in caplog.records)
