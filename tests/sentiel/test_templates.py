"""The enterprise explanations, the partition they read, and the base rates they start from.

Three things are worth stating about what these tests check, because each is a claim PART 6C makes
rather than a mechanism it inherits.

**The feature partition is checked for totality and disjointness, not for taste.** Every one of the
34 features `phos.sentiel.PEER_FEATURES` emits lands in exactly one `BehaviourFamily`, and nothing
outside that tuple lands anywhere. A partition that quietly dropped a feature would silently stop
that feature's departures from ever reaching a hypothesis, and nothing else in the system would
notice.

**The priors are checked for derivation, not for value.** Each is asserted to be exactly
``prior_at_rank(k)`` for the integer rank the module declares, so a later edit that nudges a number
to make a known case score better has to change a *rank* — a statement about base rates — rather
than a float. That is the mechanical guard behind PART 6C §9's "do not tune toward the two known
r3.1 insiders".

**The absence of contradictory patterns is asserted.** It is a finding, not an oversight: on
per-entity-window behavioural features, every family of departure is consistent with every
explanation on offer. The test pins it so that a later PART adding a contradiction has to delete an
assertion that says why there was none.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from phos.ontology import Domain, Evidence, EvidenceKind, EvidenceRole
from phos.reasoning import (
    INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
    EvidencePattern,
    HypothesisTemplate,
    ReasoningConfig,
    insufficient_evidence_template,
)
from phos.sentiel import (
    BENIGN_ROLE_CHANGE_TEMPLATE_ID,
    COMPROMISED_ACCOUNT_TEMPLATE_ID,
    ENRICHED_FEATURES,
    FEATURE_FAMILIES,
    INSIDER_MISUSE_TEMPLATE_ID,
    LOWEST_BASE_RATE_PRIOR,
    PEER_ANOMALY_TEMPLATE_ID,
    PEER_FEATURES,
    PEER_RELATIVE_FEATURES,
    RANK_ODDS_FACTOR,
    RELATIONSHIP_FEATURES,
    RESIDUAL_PRIOR,
    STARTER_FEATURES,
    BehaviourFamily,
    BehaviourFamilyPattern,
    behaviour_event_source_id,
    behaviour_family_of,
    behaviour_member_ids,
    family_of,
    is_behaviour_event,
    prior_at_rank,
    sentiel_library,
    sentiel_templates,
    user_entity_id,
)

WHEN = datetime(2010, 8, 3, tzinfo=UTC)
ENTITY = user_entity_id("CCH0959")


def _event(family: BehaviourFamily, *members: str, weight: float = 0.5) -> Evidence:
    """Return one behaviour event of ``family``, in the shape the engine emits."""
    return Evidence(
        kind=EvidenceKind.DEVIATION,
        source_id=behaviour_event_source_id(family, members or ("ev_1",)),
        entity_ids=[ENTITY],
        timestamp=WHEN,
        domain=Domain.SENTIEL,
        weight=weight,
        summary=f"{family.value} departed",
    )


def _plain(kind: EvidenceKind = EvidenceKind.DEVIATION) -> Evidence:
    """Return evidence that is not a behaviour event — a per-contribution fact, say."""
    return Evidence(
        kind=kind,
        source_id="dev_abc123",
        entity_ids=[ENTITY],
        timestamp=WHEN,
        domain=Domain.SENTIEL,
        weight=0.5,
        summary="one feature departed",
    )


# ------------------------------------------------------------------------------------------------
# The partition
# ------------------------------------------------------------------------------------------------


class TestTheFeaturePartition:
    def test_every_peer_set_feature_has_exactly_one_family(self) -> None:
        assert set(FEATURE_FAMILIES) == set(PEER_FEATURES)
        assert len(FEATURE_FAMILIES) == len(PEER_FEATURES) == 34

    def test_the_partition_names_nothing_the_featuriser_does_not_emit(self) -> None:
        """A family for a feature that is never emitted is a rule nothing will ever exercise."""
        assert not set(FEATURE_FAMILIES) - set(PEER_FEATURES)

    def test_every_family_is_used(self) -> None:
        assert set(FEATURE_FAMILIES.values()) == set(BehaviourFamily)

    def test_the_peer_family_is_exactly_the_declared_peer_relative_features(self) -> None:
        """The peer register is the one register a template discriminates on, so it is exact."""
        peers = {f for f, family in FEATURE_FAMILIES.items() if family is BehaviourFamily.PEER}
        assert peers == set(PEER_RELATIVE_FEATURES)

    def test_the_relationship_family_is_the_featurisers_own_declared_family(self) -> None:
        """6C does not re-cut this one: `RELATIONSHIP_FEATURES` already declares it."""
        found = {
            f for f, family in FEATURE_FAMILIES.items() if family is BehaviourFamily.RELATIONSHIP
        }
        assert found == set(RELATIONSHIP_FEATURES)

    def test_access_and_data_handling_partition_what_is_left(self) -> None:
        access = {f for f, fam in FEATURE_FAMILIES.items() if fam is BehaviourFamily.ACCESS}
        data = {f for f, fam in FEATURE_FAMILIES.items() if fam is BehaviourFamily.DATA_HANDLING}
        assert not access & data
        rest = set(ENRICHED_FEATURES) - set(RELATIONSHIP_FEATURES)
        assert access | data == rest

    @pytest.mark.parametrize(
        ("feature", "expected"),
        [
            ("logon_count", BehaviourFamily.ACCESS),
            ("distinct_pcs", BehaviourFamily.ACCESS),
            ("off_hours_logon_count", BehaviourFamily.ACCESS),
            ("off_hours_logon_count_dev", BehaviourFamily.ACCESS),
            ("off_hours_logon_count_trend", BehaviourFamily.ACCESS),
            ("removable_device_connects", BehaviourFamily.DATA_HANDLING),
            ("file_access_count_dev", BehaviourFamily.DATA_HANDLING),
            ("distinct_http_hosts", BehaviourFamily.DATA_HANDLING),
            ("external_email_count", BehaviourFamily.DATA_HANDLING),
            ("new_pcs", BehaviourFamily.RELATIONSHIP),
            ("new_counterparties", BehaviourFamily.RELATIONSHIP),
            ("logon_count_peer", BehaviourFamily.PEER),
        ],
    )
    def test_named_features_land_where_the_module_says(
        self, feature: str, expected: BehaviourFamily
    ) -> None:
        assert family_of(feature) is expected

    def test_a_feature_the_featuriser_does_not_emit_has_no_family(self) -> None:
        """Unknown is not "some family": guessing would put a departure in the wrong story."""
        assert family_of("cpu_temperature") is None

    def test_a_starter_count_and_its_own_deviation_share_a_family(self) -> None:
        """A level and its self-relative companion are the same behaviour measured twice."""
        for feature in STARTER_FEATURES:
            assert family_of(feature) is family_of(f"{feature}_dev")


# ------------------------------------------------------------------------------------------------
# The declared marker
# ------------------------------------------------------------------------------------------------


class TestTheBehaviourEventMarker:
    def test_a_behaviour_event_round_trips_its_family_and_its_members(self) -> None:
        event = _event(BehaviourFamily.DATA_HANDLING, "ev_1", "ev_2", "ev_3")
        assert is_behaviour_event(event)
        assert behaviour_family_of(event) is BehaviourFamily.DATA_HANDLING
        assert behaviour_member_ids(event) == ("ev_1", "ev_2", "ev_3")

    def test_a_fact_that_is_not_a_behaviour_event_carries_no_family(self) -> None:
        plain = _plain()
        assert not is_behaviour_event(plain)
        assert behaviour_family_of(plain) is None

    def test_reading_members_off_a_plain_fact_is_refused(self) -> None:
        with pytest.raises(ValueError, match="not a behaviour event"):
            behaviour_member_ids(_plain())

    def test_an_event_with_no_members_is_refused_at_construction(self) -> None:
        """An event no operator can expand back into features would be a summary, not a finding."""
        with pytest.raises(ValueError, match="at least one member"):
            behaviour_event_source_id(BehaviourFamily.ACCESS, ())

    def test_a_member_id_containing_the_separator_is_refused(self) -> None:
        with pytest.raises(ValueError, match="separator"):
            behaviour_event_source_id(BehaviourFamily.ACCESS, ("ev_1,ev_2",))

    def test_an_unrecognised_family_in_the_marker_reads_as_no_family(self) -> None:
        """Reading is total: a marker from a future version must not raise inside a matcher."""
        forged = _plain().model_copy(update={"source_id": "behaviour-event:TELEPATHY:ev_1"})
        assert is_behaviour_event(forged)
        assert behaviour_family_of(forged) is None


# ------------------------------------------------------------------------------------------------
# The pattern
# ------------------------------------------------------------------------------------------------


class TestTheBehaviourFamilyPattern:
    def test_it_matches_only_its_own_families(self) -> None:
        pattern = BehaviourFamilyPattern(
            kinds=(EvidenceKind.DEVIATION,), families=(BehaviourFamily.ACCESS,)
        )
        assert pattern.matches(_event(BehaviourFamily.ACCESS), {})
        assert not pattern.matches(_event(BehaviourFamily.PEER), {})

    def test_it_refuses_a_fact_that_carries_no_family(self) -> None:
        pattern = BehaviourFamilyPattern(families=(BehaviourFamily.ACCESS,))
        assert not pattern.matches(_plain(), {})

    def test_no_declared_family_means_no_constraint(self) -> None:
        """An empty tuple means "any", exactly as it does on the base class."""
        pattern = BehaviourFamilyPattern()
        assert pattern.matches(_event(BehaviourFamily.PEER), {})
        assert pattern.matches(_plain(), {})

    def test_the_inherited_constraints_still_apply(self) -> None:
        pattern = BehaviourFamilyPattern(
            kinds=(EvidenceKind.RELATIONSHIP_CHANGE,), families=(BehaviourFamily.ACCESS,)
        )
        assert not pattern.matches(_event(BehaviourFamily.ACCESS), {})

    def test_families_are_stored_sorted_and_deduplicated(self) -> None:
        """Two spellings of one pattern must be equal objects, as on the base class."""
        one = BehaviourFamilyPattern(families=(BehaviourFamily.PEER, BehaviourFamily.ACCESS))
        other = BehaviourFamilyPattern(
            families=(BehaviourFamily.ACCESS, BehaviourFamily.PEER, BehaviourFamily.ACCESS)
        )
        assert one == other

    def test_disjoint_families_cannot_both_match_one_fact(self) -> None:
        access = BehaviourFamilyPattern(families=(BehaviourFamily.ACCESS,))
        peer = BehaviourFamilyPattern(families=(BehaviourFamily.PEER,))
        assert not access.overlaps(peer)
        assert not peer.overlaps(access)

    def test_shared_families_overlap(self) -> None:
        one = BehaviourFamilyPattern(
            families=(BehaviourFamily.ACCESS, BehaviourFamily.DATA_HANDLING)
        )
        other = BehaviourFamilyPattern(families=(BehaviourFamily.DATA_HANDLING,))
        assert one.overlaps(other)

    def test_an_unconstrained_pattern_overlaps_everything(self) -> None:
        assert BehaviourFamilyPattern().overlaps(
            BehaviourFamilyPattern(families=(BehaviourFamily.PEER,))
        )
        assert BehaviourFamilyPattern(families=(BehaviourFamily.PEER,)).overlaps(EvidencePattern())

    def test_a_disjoint_kind_still_separates_two_patterns_of_one_family(self) -> None:
        one = BehaviourFamilyPattern(
            kinds=(EvidenceKind.DEVIATION,), families=(BehaviourFamily.ACCESS,)
        )
        other = BehaviourFamilyPattern(
            kinds=(EvidenceKind.FORECAST_MISS,), families=(BehaviourFamily.ACCESS,)
        )
        assert not one.overlaps(other)

    def test_a_template_may_not_call_one_family_both_supporting_and_contradictory(self) -> None:
        """The base guarantee must survive the subclass, or a role is not single-valued."""
        with pytest.raises(ValidationError, match="both support and contradict"):
            HypothesisTemplate(
                template_id="confused",
                label="Confused",
                domain=Domain.SENTIEL,
                prior=0.1,
                supported_by=(BehaviourFamilyPattern(families=(BehaviourFamily.ACCESS,)),),
                contradicted_by=(
                    BehaviourFamilyPattern(families=(BehaviourFamily.ACCESS, BehaviourFamily.PEER)),
                ),
            )

    def test_disjoint_families_let_a_template_construct(self) -> None:
        template = HypothesisTemplate(
            template_id="fine",
            label="Fine",
            domain=Domain.SENTIEL,
            prior=0.1,
            supported_by=(BehaviourFamilyPattern(families=(BehaviourFamily.ACCESS,)),),
            contradicted_by=(BehaviourFamilyPattern(families=(BehaviourFamily.PEER,)),),
        )
        assert template.role_for(_event(BehaviourFamily.ACCESS), {}) is EvidenceRole.SUPPORTING
        assert template.role_for(_event(BehaviourFamily.PEER), {}) is EvidenceRole.CONTRADICTORY

    def test_the_subclass_survives_being_stored_on_a_template(self) -> None:
        """Pydantic must not coerce the subclass away, or every family constraint would vanish."""
        template = HypothesisTemplate(
            template_id="kept",
            label="Kept",
            domain=Domain.SENTIEL,
            prior=0.1,
            supported_by=(BehaviourFamilyPattern(families=(BehaviourFamily.PEER,)),),
        )
        assert isinstance(template.supported_by[0], BehaviourFamilyPattern)
        assert template.role_for(_event(BehaviourFamily.ACCESS), {}) is None


# ------------------------------------------------------------------------------------------------
# The base-rate ladder
# ------------------------------------------------------------------------------------------------


class TestThePriorLadder:
    def test_rank_zero_is_the_engines_own_pruning_threshold(self) -> None:
        """The rarest explanation starts exactly where the engine stops considering one."""
        assert prior_at_rank(0) == pytest.approx(LOWEST_BASE_RATE_PRIOR)
        assert LOWEST_BASE_RATE_PRIOR == ReasoningConfig().pruning_threshold

    def test_each_rank_multiplies_the_odds_by_one_piece_of_evidence(self) -> None:
        for rank in range(2):
            low, high = prior_at_rank(rank), prior_at_rank(rank + 1)
            assert (high / (1 - high)) == pytest.approx((low / (1 - low)) * RANK_ODDS_FACTOR)

    def test_a_negative_rank_is_refused(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            prior_at_rank(-1)

    def test_a_rank_that_would_start_ahead_of_the_residual_is_refused(self) -> None:
        """No offered explanation may lead before any evidence; that place is the residual's."""
        with pytest.raises(ValueError, match="insufficient evidence"):
            prior_at_rank(3)

    def test_the_residual_prior_is_read_from_the_shared_template_not_restated(self) -> None:
        assert RESIDUAL_PRIOR == insufficient_evidence_template(Domain.SENTIEL).prior


# ------------------------------------------------------------------------------------------------
# The five explanations
# ------------------------------------------------------------------------------------------------


class TestTheEnterpriseTemplates:
    def test_there_are_five_and_they_are_all_sentiel(self) -> None:
        templates = sentiel_templates()
        assert len(templates) == 5
        assert all(template.domain is Domain.SENTIEL for template in templates)

    def test_the_residual_is_among_them(self) -> None:
        ids = [template.template_id for template in sentiel_templates()]
        assert INSUFFICIENT_EVIDENCE_TEMPLATE_ID in ids

    def test_they_are_registered_most_common_first(self) -> None:
        ids = [template.template_id for template in sentiel_templates()]
        assert ids == [
            BENIGN_ROLE_CHANGE_TEMPLATE_ID,
            PEER_ANOMALY_TEMPLATE_ID,
            COMPROMISED_ACCOUNT_TEMPLATE_ID,
            INSIDER_MISUSE_TEMPLATE_ID,
            INSUFFICIENT_EVIDENCE_TEMPLATE_ID,
        ]

    def test_the_priors_are_base_rate_ordered_benign_above_malicious(self) -> None:
        priors = {t.template_id: t.prior for t in sentiel_templates()}
        assert priors[BENIGN_ROLE_CHANGE_TEMPLATE_ID] > priors[COMPROMISED_ACCOUNT_TEMPLATE_ID]
        assert priors[PEER_ANOMALY_TEMPLATE_ID] > priors[COMPROMISED_ACCOUNT_TEMPLATE_ID]
        assert priors[COMPROMISED_ACCOUNT_TEMPLATE_ID] > priors[INSIDER_MISUSE_TEMPLATE_ID]

    @pytest.mark.parametrize(
        ("template_id", "rank"),
        [
            (BENIGN_ROLE_CHANGE_TEMPLATE_ID, 2),
            (PEER_ANOMALY_TEMPLATE_ID, 2),
            (COMPROMISED_ACCOUNT_TEMPLATE_ID, 1),
            (INSIDER_MISUSE_TEMPLATE_ID, 0),
        ],
    )
    def test_every_prior_is_a_declared_rank_and_not_a_free_float(
        self, template_id: str, rank: int
    ) -> None:
        """PART 6C §9: a later edit must move a base-rate rank, not nudge a number to fit a case."""
        prior = {t.template_id: t.prior for t in sentiel_templates()}[template_id]
        assert prior == pytest.approx(prior_at_rank(rank))

    def test_no_explanation_starts_ahead_of_insufficient_evidence(self) -> None:
        for template in sentiel_templates():
            if template.template_id == INSUFFICIENT_EVIDENCE_TEMPLATE_ID:
                continue
            assert template.prior < RESIDUAL_PRIOR

    def test_no_explanation_is_born_pruned(self) -> None:
        threshold = ReasoningConfig().pruning_threshold
        assert all(template.prior >= threshold for template in sentiel_templates())

    def test_the_residual_declares_no_patterns(self) -> None:
        residual = sentiel_library().residual_for(Domain.SENTIEL)
        assert not residual.supported_by
        assert not residual.contradicted_by

    @pytest.mark.parametrize(
        ("template_id", "family"),
        [
            (BENIGN_ROLE_CHANGE_TEMPLATE_ID, BehaviourFamily.RELATIONSHIP),
            (PEER_ANOMALY_TEMPLATE_ID, BehaviourFamily.PEER),
            (COMPROMISED_ACCOUNT_TEMPLATE_ID, BehaviourFamily.ACCESS),
            (INSIDER_MISUSE_TEMPLATE_ID, BehaviourFamily.DATA_HANDLING),
        ],
    )
    def test_each_explanation_is_supported_by_the_family_that_discriminates_it(
        self, template_id: str, family: BehaviourFamily
    ) -> None:
        library = sentiel_library()
        template = library.get(template_id, Domain.SENTIEL)
        assert template is not None
        assert template.role_for(_event(family), {}) is EvidenceRole.SUPPORTING

    def test_each_explanation_ignores_the_other_families(self) -> None:
        """A template supported by everything is separated from its rivals only by its prior."""
        supporters: dict[BehaviourFamily, set[str]] = {family: set() for family in BehaviourFamily}
        for template in sentiel_templates():
            for family in BehaviourFamily:
                if template.role_for(_event(family), {}) is EvidenceRole.SUPPORTING:
                    supporters[family].add(template.template_id)
        assert supporters == {
            BehaviourFamily.RELATIONSHIP: {BENIGN_ROLE_CHANGE_TEMPLATE_ID},
            BehaviourFamily.PEER: {PEER_ANOMALY_TEMPLATE_ID},
            BehaviourFamily.ACCESS: {COMPROMISED_ACCOUNT_TEMPLATE_ID},
            BehaviourFamily.DATA_HANDLING: {INSIDER_MISUSE_TEMPLATE_ID},
        }

    def test_no_template_declares_a_contradictory_pattern(self) -> None:
        """A finding, not an omission — see this module's docstring and ADR 0023.

        On per-entity-window behavioural features every family of departure is consistent with
        every explanation on offer: a sanctioned role change genuinely moves access and data
        handling, and an insider genuinely acquires new counterparties. Inventing a contradiction
        to look sophisticated would make the engine argue against an explanation the evidence does
        not argue against.
        """
        assert all(not template.contradicted_by for template in sentiel_templates())

    def test_evidence_from_another_engine_bears_on_nothing(self) -> None:
        """Cross-engine correlation is PART 7's job, not a template's."""
        atlas_fact = _event(BehaviourFamily.ACCESS).model_copy(update={"domain": Domain.ATLAS})
        for template in sentiel_templates():
            assert template.role_for(atlas_fact, {}) is None

    def test_the_library_holds_exactly_the_templates(self) -> None:
        library = sentiel_library()
        assert library.templates == sentiel_templates()
        assert library.for_domain(Domain.SENTIEL) == sentiel_templates()
        assert library.for_domain(Domain.ATLAS) == ()

    def test_a_per_contribution_fact_bears_on_nothing(self) -> None:
        """Only grouped behaviour events are reasoned over; the members underneath are traceability.

        If a member fact reached the reasoning engine it would be counted twice — once itself and
        once inside its event — and a wide feature set would inflate confidence exactly as PART 6A
        found it inflating alerts.
        """
        for template in sentiel_templates():
            assert template.role_for(_plain(), {}) is None
