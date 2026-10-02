"""IT library: hundreds of person-days, entity-scoped labels, busy days are not labelled theft."""

from phos.eval import Dataset, EvalConfig
from phos.library.it import (
    generate_it_observations,
    it_catalogue_payload,
    it_person_days,
    it_personas,
)
from phos.models import GaussianBaseline
from phos.ontology import Domain
from phos.sentiel import (
    AggregatedDetector,
    evaluate_entity_aware,
    malicious_user_ids,
    precision_policy,
    static_range_model,
    user_entity_id,
)


def test_the_population_is_dozens_of_people_and_hundreds_of_person_days() -> None:
    personas = it_personas()
    assert len(personas) >= 40
    assert it_person_days(personas) >= 200
    labelled = [persona for persona in personas if persona.labelled]
    assert len(labelled) >= 6
    assert all(persona.kind != "normal" for persona in labelled)


def test_the_catalogue_says_these_are_personas_we_wrote() -> None:
    payload = it_catalogue_payload()
    caveats = payload["caveats"]
    assert isinstance(caveats, list)
    joined = " ".join(str(item) for item in caveats)
    assert "BEHAVIOURAL FIXTURES" in joined
    assert payload["n_person_days"] == it_person_days()


def test_observations_are_time_ordered_and_labels_are_entity_scoped() -> None:
    observations, labels = generate_it_observations()
    stamps = [item.timestamp for item in observations]
    assert stamps == sorted(stamps)
    assert observations[0].entity_ids[0] == user_entity_id(it_personas()[0].user_id)
    ids = malicious_user_ids(labels)
    assert "M00" in ids
    assert "N00" not in ids
    assert all(label.release == "library-it" for label in labels)


def test_backup_team_is_loud_on_files_and_quiet_on_peers_in_the_test_half() -> None:
    observations, _labels = generate_it_observations()
    backup = [
        item
        for item in observations
        if item.entity_ids[0] == user_entity_id("B00") and item.feature == "file_access_count"
    ]
    peer = [
        item
        for item in observations
        if item.entity_ids[0] == user_entity_id("B00") and item.feature == "file_access_count_peer"
    ]
    train_files = [item.value for item in backup[:35]]
    test_files = [item.value for item in backup[35:]]
    test_peer = [item.value for item in peer[35:]]
    assert max(test_files) > max(train_files) + 10.0
    assert max(test_peer) < min(test_files)


def test_precision_chronic_ranks_an_insider_above_a_backup_week() -> None:
    observations, labels = generate_it_observations()
    test_start = labels[0].start
    train = [item for item in observations if item.timestamp < test_start]
    test = [item for item in observations if item.timestamp >= test_start]
    fitted = static_range_model(GaussianBaseline(min_samples=8).fit(train))
    detector = AggregatedDetector(
        fitted=fitted, policy=precision_policy(chronic_volume_halflife_days=4.0)
    )
    dataset = Dataset(
        name="it-probe",
        domain=Domain.SENTIEL,
        observations=test,
    )
    report = evaluate_entity_aware(
        detector, dataset, labels, EvalConfig(alert_threshold=1.25, seed=11)
    )
    assert report.window_recall >= 0.5
    assert report.precision > 0.0
