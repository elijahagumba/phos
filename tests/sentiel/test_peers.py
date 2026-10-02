"""Peer groups and peer baselines: declared, causal, leave-one-out, and silent when they must be.

The four load-bearing properties, each with a test written to fail on the implementation that
loses it:

- **Declared, not inferred.** Groups come from the directory. No amount of behaviour moves anybody.
- **Causal.** A window is judged against peers' *earlier* windows only — including the peers who
  acted in the very same window, which is the leak a per-user ``observe`` would introduce.
- **Leave-one-out.** A user is never part of the distribution they are judged against.
- **Silent when it must be.** Too small a group, or no group at all, emits nothing — not a zero,
  not a ``NaN``, not a fabricated baseline.
"""

import math
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from phos.ontology import Domain, Entity, EntityType
from phos.sentiel import (
    DEFAULT_GROUP_ATTRIBUTE,
    NEUTRAL_VALUE,
    EntityCatalogue,
    HistoryPolicy,
    PeerGroups,
    PeerHistory,
    PeerPolicy,
    user_entity_id,
)

FEATURES = ("logon_count", "file_access_count")
STAMP = datetime(2010, 1, 4, tzinfo=UTC)


def _entity(user_id: str, **attributes: str) -> Entity:
    """Return a catalogued entity carrying the given directory attributes."""
    return Entity(
        id=user_entity_id(user_id),
        type=EntityType.USER,
        domain=Domain.SENTIEL,
        name=user_id,
        attributes=attributes,
        created_at=STAMP,
    )


def _catalogue(**roles: str) -> EntityCatalogue:
    """Return a catalogue of ``user_id=role`` pairs; an empty role means the column was blank."""
    return EntityCatalogue(
        entities={
            user_id: _entity(user_id, **({"role": role} if role else {}))
            for user_id, role in roles.items()
        },
        directory_as_of=STAMP,
        snapshots_read=1,
    )


def _groups(size: int = 5, attribute: str = DEFAULT_GROUP_ATTRIBUTE, **roles: str) -> PeerGroups:
    """Return groups cut from a catalogue of ``user_id=role`` pairs."""
    return PeerGroups.from_catalogue(
        _catalogue(**roles), PeerPolicy(group_attribute=attribute, min_group_size=size)
    )


def _team(name: str, count: int, start: int = 0) -> dict[str, str]:
    """Return ``count`` users all declared into the group ``name``."""
    return {f"{name}{index:02d}": name for index in range(start, start + count)}


# ------------------------------------------------------------------------------------------------
# Declared, not inferred — acceptance criterion 2
# ------------------------------------------------------------------------------------------------


class TestGroupsAreDeclaredNotInferred:
    """A peer group is a fact about the directory, and there is no path from behaviour to it."""

    def test_it_groups_by_the_declared_attribute(self) -> None:
        groups = _groups(size=2, ALICE="Salesman", BOB="Salesman", CARA="ITAdmin", DAN="ITAdmin")
        assert groups.group_of("ALICE") == "Salesman"
        assert groups.group_of("CARA") == "ITAdmin"

    def test_behaviour_cannot_move_anybody(self) -> None:
        """The only input is the catalogue, so a wildly different corpus gives identical groups.

        This is the circularity PART 6B refuses. A group inferred from behaviour would define
        "normal" using the very anomaly being hunted: put the three users who exfiltrate together
        and exfiltration becomes their group's normal.
        """
        catalogue = _catalogue(ALICE="Salesman", BOB="Salesman", CARA="Salesman")
        quiet = PeerGroups.from_catalogue(catalogue, PeerPolicy(min_group_size=2))

        history = PeerHistory(quiet, FEATURES, HistoryPolicy(min_history_windows=1))
        for _ in range(40):
            history.observe({"ALICE": (1.0, 1.0), "BOB": (1.0, 1.0), "CARA": (9_999.0, 9_999.0)})

        assert PeerGroups.from_catalogue(catalogue, PeerPolicy(min_group_size=2)) == quiet
        assert history.groups == quiet

    def test_changing_the_declared_attribute_is_what_moves_somebody(self) -> None:
        before = _groups(size=2, ALICE="Salesman", BOB="Salesman", CARA="ITAdmin", DAN="ITAdmin")
        after = _groups(size=2, ALICE="ITAdmin", BOB="Salesman", CARA="ITAdmin", DAN="ITAdmin")
        assert before.group_of("ALICE") == "Salesman"
        assert after.group_of("ALICE") == "ITAdmin"

    def test_a_different_attribute_cuts_different_groups(self) -> None:
        catalogue = EntityCatalogue(
            entities={
                "ALICE": _entity("ALICE", role="Salesman", team="Team A"),
                "BOB": _entity("BOB", role="ITAdmin", team="Team A"),
            },
            directory_as_of=STAMP,
        )
        by_role = PeerGroups.from_catalogue(catalogue, PeerPolicy(min_group_size=2))
        by_team = PeerGroups.from_catalogue(
            catalogue, PeerPolicy(group_attribute="team", min_group_size=2)
        )
        assert by_role.group_of("ALICE") is None  # two roles, one member each
        assert by_team.group_of("ALICE") == by_team.group_of("BOB") == "Team A"

    def test_an_attribute_nobody_carries_is_refused_at_construction(self) -> None:
        """Silent and permanent is worse than a crash: no peer feature would ever be emitted."""
        with pytest.raises(ValueError, match="no catalogued user carries the attribute"):
            _groups(size=2, attribute="favourite_colour", ALICE="Salesman", BOB="Salesman")

    def test_an_unnamed_attribute_is_refused(self) -> None:
        with pytest.raises(ValidationError, match=r"must name an Entity\.attributes key"):
            PeerPolicy(group_attribute="   ")

    def test_a_group_of_one_is_refused_as_a_minimum(self) -> None:
        with pytest.raises(ValidationError):
            PeerPolicy(min_group_size=1)


# ------------------------------------------------------------------------------------------------
# The small-group and no-group policies — acceptance criterion 3
# ------------------------------------------------------------------------------------------------


class TestTheSmallAndNoGroupPolicies:
    """Unknown is not anomalous, so an entity without peers gets no peer feature at all."""

    def test_a_group_exactly_at_the_minimum_is_used(self) -> None:
        groups = _groups(size=5, **_team("Sales", 5))
        assert groups.group_of("Sales00") == "Sales"
        assert groups.usable_groups == 1

    def test_a_group_one_short_of_the_minimum_is_not(self) -> None:
        """The boundary, stated as a pair so an off-by-one cannot pass."""
        groups = _groups(size=5, **_team("Sales", 4))
        assert groups.group_of("Sales00") is None
        assert groups.usable_groups == 0
        assert groups.declared_sizes == {"Sales": 4}, "the small group is still reported"
        assert groups.ungrouped == 4

    def test_a_user_with_no_value_for_the_attribute_has_no_group(self) -> None:
        roles = _team("Sales", 5)
        roles["NOBODY"] = ""
        groups = _groups(size=5, **roles)
        assert groups.group_of("NOBODY") is None
        assert groups.ungrouped == 1

    def test_a_membership_that_breaks_the_minimum_cannot_be_constructed_at_all(self) -> None:
        """The gate is an invariant of the type, not a rule `from_catalogue` happens to apply."""
        with pytest.raises(ValidationError, match="3 declared member"):
            PeerGroups(
                group_attribute="role",
                min_group_size=5,
                membership={"A": "Sales"},
                declared_sizes={"Sales": 3},
            )

    def test_a_membership_naming_an_unknown_group_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="declared_sizes does not name"):
            PeerGroups(group_attribute="role", min_group_size=2, membership={"A": "Ghost"})

    def test_a_user_absent_from_the_directory_has_no_group(self) -> None:
        groups = _groups(size=5, **_team("Sales", 5))
        assert groups.group_of("NEVER_HEARD_OF_THEM") is None

    @pytest.mark.parametrize("feature", FEATURES)
    def test_an_ungrouped_user_gets_none_rather_than_a_number(self, feature: str) -> None:
        """`None` is the signal to emit no observation. A zero would be a fabricated measurement."""
        history = PeerHistory(_groups(size=5, **_team("Sales", 5)), FEATURES)
        assert history.deviation("NOBODY", feature, 1_000.0) is None

    def test_no_read_is_ever_nan_or_infinite(self) -> None:
        """Whatever the pool looks like, an `Observation` must be able to carry the answer."""
        history = PeerHistory(
            _groups(size=5, **_team("Sales", 5)), FEATURES, HistoryPolicy(min_history_windows=1)
        )
        for step in range(12):
            history.observe({f"Sales{index:02d}": (0.0, float(step)) for index in range(5)})
        for feature in FEATURES:
            for value in (0.0, -1e9, 1e9):
                answer = history.deviation("Sales00", feature, value)
                assert answer is not None
                assert math.isfinite(answer)


# ------------------------------------------------------------------------------------------------
# Causality — acceptance criterion 1, the load-bearing one
# ------------------------------------------------------------------------------------------------


class TestPeerCausality:
    """A window's peer baseline holds every earlier window and no part of the window itself."""

    def _history(self) -> PeerHistory:
        return PeerHistory(_groups(size=5, **_team("Sales", 5)), FEATURES, HistoryPolicy())

    def test_the_cohorts_own_window_is_not_in_the_baseline_it_is_judged_against(self) -> None:
        """The leak this is written to catch, with the two answers far enough apart to see.

        Four peers sit at 10 for eight windows and then all jump to 100 on the ninth, while the
        subject stays at 10. Causally the subject's pool for that ninth window is nothing but tens,
        so a value of 10 is exactly the peer mean and the answer is 0.0. Had the ninth window been
        folded in before it was read — which is what a per-user ``observe`` would do — the pool
        would hold four hundreds, the subject would sit far below its mean, and the answer would be
        a large negative number. A leak here produces no error and no absurd value; it just quietly
        moves the peer mean toward the very cohort being judged.
        """
        history = self._history()
        for _ in range(8):
            history.observe({f"Sales{index:02d}": (10.0, 10.0) for index in range(5)})

        during = history.deviation("Sales04", "logon_count", 10.0)
        history.observe(
            {**{f"Sales{index:02d}": (100.0, 100.0) for index in range(4)}, "Sales04": (10.0, 10.0)}
        )
        after = history.deviation("Sales04", "logon_count", 10.0)

        assert during == 0.0, "the same window's peers must not be in its own baseline"
        assert after is not None and after < 0.0, "and must be in the next window's"
        # The size of `after` is modest — one window of four peers against a pool of nine windows
        # — and deliberately not asserted. The causal fact under test is that it is zero before the
        # jump is folded in and negative afterwards, in that order.

    def test_no_peer_data_at_all_reads_as_neutral_not_as_a_departure(self) -> None:
        history = self._history()
        assert history.deviation("Sales00", "logon_count", 5_000.0) == NEUTRAL_VALUE

    def test_the_pool_is_bounded_so_the_distant_past_falls_out(self) -> None:
        """A group that changes what it does stops being judged against what it used to do."""
        history = PeerHistory(
            _groups(size=5, **_team("Sales", 5)),
            FEATURES,
            HistoryPolicy(trailing_windows=10, min_history_windows=8),
        )
        for _ in range(10):
            history.observe({f"Sales{index:02d}": (10.0, 10.0) for index in range(5)})
        for _ in range(10):
            history.observe({f"Sales{index:02d}": (500.0, 500.0) for index in range(5)})
        answer = history.deviation("Sales04", "logon_count", 500.0)
        assert answer == 0.0, "the tens have fallen out; 500 is now the group's normal"


class TestAMemberWhoStopsContributingFallsOut:
    """The pool is bounded in people as well as in windows."""

    def test_a_member_is_forgotten_once_their_last_window_is_evicted(self) -> None:
        """Somebody who leaves the team stops counting as a peer, rather than lingering forever."""
        history = PeerHistory(
            _groups(size=5, **_team("Sales", 6)),
            FEATURES,
            HistoryPolicy(trailing_windows=6, min_history_windows=1),
        )
        history.observe(
            {**{f"Sales{index:02d}": (10.0, 10.0) for index in range(5)}, "Sales05": (1_000.0, 0.0)}
        )
        while_present = history.deviation("Sales04", "logon_count", 10.0)
        for _ in range(6):
            history.observe({f"Sales{index:02d}": (10.0, 10.0) for index in range(5)})

        assert while_present is not None and while_present < 0.0, "Sales05 pulls the mean up"
        assert history.deviation("Sales04", "logon_count", 10.0) == 0.0, (
            "their only window has fallen out, so the pool is nothing but tens again"
        )

    def test_a_pool_holding_only_the_subject_says_nothing(self) -> None:
        history = PeerHistory(
            _groups(size=5, **_team("Sales", 5)), FEATURES, HistoryPolicy(min_history_windows=1)
        )
        for _ in range(10):
            history.observe({"Sales04": (10.0, 10.0)})
        assert history.deviation("Sales04", "logon_count", 900.0) == NEUTRAL_VALUE


class TestTheBaselineLeavesTheEntityOut:
    """A user is never part of the distribution they are judged against."""

    def test_a_users_own_past_does_not_soften_their_own_peer_deviation(self) -> None:
        """Left in, the subject's own history would be a fifth of the pool and pull it up.

        Leaving it out is what keeps this family orthogonal to `phos.sentiel.history`'s ``_dev``
        family, which already answers "unlike your own past". A blend of the two questions would
        cost the multiplicity of eight more features to re-ask one already answered.
        """
        history = PeerHistory(
            _groups(size=5, **_team("Sales", 5)), FEATURES, HistoryPolicy(min_history_windows=4)
        )
        for _ in range(10):
            history.observe(
                {
                    **{f"Sales{index:02d}": (10.0, 10.0) for index in range(4)},
                    "Sales04": (100.0, 100.0),
                }
            )
        answer = history.deviation("Sales04", "logon_count", 100.0)
        assert answer == 10.0, "peers never varied from 10, so 100 is at the cap, signed positive"

    def test_a_peer_is_judged_against_the_others_including_the_odd_one_out(self) -> None:
        history = PeerHistory(
            _groups(size=5, **_team("Sales", 5)), FEATURES, HistoryPolicy(min_history_windows=4)
        )
        for _ in range(10):
            history.observe(
                {
                    **{f"Sales{index:02d}": (10.0, 10.0) for index in range(4)},
                    "Sales04": (100.0, 100.0),
                }
            )
        answer = history.deviation("Sales00", "logon_count", 10.0)
        assert answer is not None
        assert answer < 0.0, "Sales00's pool holds three tens and ten hundreds, so 10 is below it"


# ------------------------------------------------------------------------------------------------
# Cold start, zero spread and the cap — 6A's policies, applied one level out
# ------------------------------------------------------------------------------------------------


class TestTheColdStartAndZeroSpreadPolicies:
    """The pool speaks only when it can, and never divides by a spread of zero."""

    def test_too_few_samples_reads_as_neutral(self) -> None:
        history = PeerHistory(
            _groups(size=5, **_team("Sales", 5)), FEATURES, HistoryPolicy(min_history_windows=8)
        )
        history.observe({f"Sales{index:02d}": (10.0, 10.0) for index in range(5)})
        assert history.deviation("Sales04", "logon_count", 900.0) == NEUTRAL_VALUE

    def test_too_few_distinct_peers_reads_as_neutral_however_long_the_history(self) -> None:
        """Thirty windows of one colleague is not a peer group, and sample count cannot say so.

        This is why `PeerPolicy.min_group_size` is about *people* while
        `HistoryPolicy.min_history_windows` is about *points*: the pool below has forty samples and
        exactly one other person in it.
        """
        history = PeerHistory(_groups(size=5, **_team("Sales", 5)), FEATURES, HistoryPolicy())
        for _ in range(40):
            history.observe({"Sales00": (10.0, 10.0), "Sales04": (10.0, 10.0)})
        assert history.deviation("Sales04", "logon_count", 900.0) == NEUTRAL_VALUE

    def test_peers_who_never_varied_report_the_cap_signed(self) -> None:
        history = PeerHistory(
            _groups(size=5, **_team("Sales", 5)),
            FEATURES,
            HistoryPolicy(min_history_windows=4, deviation_cap=7.5),
        )
        for _ in range(8):
            history.observe({f"Sales{index:02d}": (10.0, 10.0) for index in range(5)})
        assert history.deviation("Sales04", "logon_count", 99.0) == 7.5
        assert history.deviation("Sales04", "logon_count", 1.0) == -7.5
        assert history.deviation("Sales04", "logon_count", 10.0) == 0.0

    def test_a_finite_deviation_is_clamped_to_the_cap(self) -> None:
        history = PeerHistory(
            _groups(size=5, **_team("Sales", 5)),
            FEATURES,
            HistoryPolicy(min_history_windows=4, deviation_cap=3.0),
        )
        for step in range(8):
            history.observe({f"Sales{index:02d}": (10.0 + index + step, 0.0) for index in range(5)})
        answer = history.deviation("Sales04", "logon_count", 10_000.0)
        assert answer == 3.0


# ------------------------------------------------------------------------------------------------
# Refusals, and the line a report carries
# ------------------------------------------------------------------------------------------------


class TestPeerHistoryRefusesTheUnanswerable:
    def test_it_needs_at_least_one_feature(self) -> None:
        with pytest.raises(ValueError, match="at least one feature"):
            PeerHistory(_groups(size=5, **_team("Sales", 5)), ())

    def test_it_refuses_a_repeated_feature(self) -> None:
        with pytest.raises(ValueError, match="duplicates"):
            PeerHistory(_groups(size=5, **_team("Sales", 5)), ("logon_count", "logon_count"))

    def test_it_refuses_a_window_of_the_wrong_width(self) -> None:
        """Silently accepting it would attribute one feature's value to another."""
        history = PeerHistory(_groups(size=5, **_team("Sales", 5)), FEATURES)
        with pytest.raises(ValueError, match="pools 2 feature"):
            history.observe({"Sales00": (1.0,)})

    def test_a_feature_it_does_not_pool_is_an_error_not_a_neutral(self) -> None:
        history = PeerHistory(_groups(size=5, **_team("Sales", 5)), FEATURES)
        with pytest.raises(KeyError):
            history.deviation("Sales00", "not_a_pooled_feature", 1.0)

    def test_ungrouped_users_are_not_pooled(self) -> None:
        """Pooling them would put a person into a distribution nobody is judged against."""
        history = PeerHistory(
            _groups(size=5, **{**_team("Sales", 5), "NOBODY": ""}),
            FEATURES,
            HistoryPolicy(min_history_windows=4),
        )
        for _ in range(8):
            history.observe(
                {
                    **{f"Sales{index:02d}": (10.0, 10.0) for index in range(5)},
                    "NOBODY": (9_999.0, 9_999.0),
                }
            )
        assert history.deviation("Sales04", "logon_count", 10.0) == 0.0


class TestTheGroupingSummary:
    def test_it_states_the_attribute_the_minimum_and_the_coverage(self) -> None:
        groups = _groups(size=5, **{**_team("Sales", 6), **_team("Ops", 3)})
        summary = groups.summary()
        assert "role" in summary
        assert "5-member minimum" in summary
        assert "1 of 2 groups" in summary
        assert "6 users" in summary
        assert "3 ungrouped" in summary
