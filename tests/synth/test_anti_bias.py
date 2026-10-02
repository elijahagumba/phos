"""The anti-bias construction: five mechanisms that make circularity fail loudly.

The risk this file exists for. If one author writes both "an attack looks like this" and "the
detector looks for that", then a good score measures the agreement of two beliefs and not
detection. The repository already refuses this one level down — topology is declared and never
clustered, peer groups come from the directory and never from behaviour. These are the same
refusal one level up, and they are **mechanisms rather than intentions**: each one fails a build.

1. The generator may not reference the detector. Checked by parsing every module under
   `src/phos/synth/` and looking at what it imports and what names it mentions.
2. Attacks are specified by physical or operational intent, never by signature. Checked by
   scanning every scenario's prose against the names Atlas itself exports.
3. Every scenario carries real-world provenance. Checked over the catalogue.
4. Every run must produce cases the detector should miss, and benign cases that should tempt it.
   Checked by generating one.
5. The method, including its failures, is published. Checked as a document with required sections.

The one allowed exception is documented in `ALLOWED_ATLAS_IMPORTS` below, and the test names it
explicitly rather than pattern-matching around it.
"""

import ast
import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy
import pytest

import phos.atlas.packet as atlas_packet
from phos.synth.catalogue_scenarios import SCENARIOS, scenarios_for
from phos.synth.maintenance import MaintenancePractice, plan_maintenance
from phos.synth.plant import RunSpec
from phos.synth.realism import PhenomenonKind, RealismProfile, plan_realism
from phos.synth.scenarios import Provenance, ProvenanceKind, Scenario

GENERATOR_ROOT = Path(__file__).resolve().parents[2] / "src" / "phos" / "synth"
METHOD_DOC = Path(__file__).resolve().parents[2] / "docs" / "synthetic-harness-method.md"

ALLOWED_ATLAS_IMPORTS = {
    "phos.atlas.topology": frozenset({"SCHEMA_VERSION", "Subsystem", "SubsystemMap"}),
}
"""The single permitted detector import, and exactly which names it may take.

`phos.synth.topology` writes the declared subsystem map in the format
`phos.atlas.topology.load_topology` reads, so a generated corpus ships its topology exactly as HAI
does. That is a **declaration format**, not a detection concept: it carries no feature, no score,
no threshold and no finding. Allowing it by name — rather than allowing the `phos.atlas` package
and hoping — is what keeps the exception from widening. Anything else under `phos.atlas` or
`phos.sentiel`, including any other name from this same module, fails the test below.
"""

DETECTION_CONCEPTS = frozenset(
    {
        "mahalanobis",
        "deviation",
        "expectedrange",
        "baseline",
        "anomaly",
        "detector",
        "detection",
        "threshold",
        "score",
        "recall",
        "false_positive",
        "hypothesis",
        "template",
        "evidence",
        "calibrat",
    }
)
"""Words that name what a detector does. A scenario using one is describing the detector."""


def generator_modules() -> list[Path]:
    """Return every module under the generator root."""
    return sorted(path for path in GENERATOR_ROOT.rglob("*.py") if "__pycache__" not in str(path))


def imported_targets(tree: ast.Module) -> list[tuple[str, tuple[str, ...]]]:
    """Return ``(module, imported names)`` for every import statement in a parsed module."""
    found: list[tuple[str, tuple[str, ...]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.module, tuple(alias.name for alias in node.names)))
        elif isinstance(node, ast.Import):
            found.extend((alias.name, ()) for alias in node.names)
    return found


class TestOneTheGeneratorMayNotReferenceTheDetector:
    """Mechanism 1. The generator knows physics, process rules and protocol. Not what Atlas does."""

    def test_the_generator_has_modules_to_check(self) -> None:
        """Guards the rest: a glob that silently matched nothing would pass everything below."""
        assert len(generator_modules()) > 10

    def test_no_generator_module_imports_a_detector_beyond_the_declared_exception(self) -> None:
        offences: list[str] = []
        for path in generator_modules():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for module, names in imported_targets(tree):
                if not (module.startswith("phos.atlas") or module.startswith("phos.sentiel")):
                    continue
                allowed = ALLOWED_ATLAS_IMPORTS.get(module)
                if allowed is None:
                    offences.append(f"{path.name} imports {module}")
                    continue
                for name in names:
                    if name not in allowed:
                        offences.append(f"{path.name} imports {name!r} from {module}")
        assert offences == [], (
            "the generator must not reference the detector; only the declared "
            f"declaration-format exception is allowed. Offences: {offences}"
        )

    def test_the_allowed_exception_is_actually_used(self) -> None:
        """A dead allowlist entry would quietly widen over time. This keeps it honest."""
        used = {
            module
            for path in generator_modules()
            for module, _ in imported_targets(ast.parse(path.read_text(encoding="utf-8")))
        }
        assert set(ALLOWED_ATLAS_IMPORTS) <= used

    def test_the_command_layer_imports_no_detector_at_all(self) -> None:
        """The modules this work added carry no exception. Checked separately so none is added."""
        added = ("command.py", "maintenance.py", "scenarios.py", "realism.py")
        for name in added:
            tree = ast.parse((GENERATOR_ROOT / name).read_text(encoding="utf-8"))
            modules = [module for module, _ in imported_targets(tree)]
            assert not [m for m in modules if m.startswith(("phos.atlas", "phos.sentiel"))]

    def test_the_maintenance_generator_cannot_see_an_attack(self) -> None:
        """Mechanism 3's other half: the calendar's own signature refuses the schedule."""
        parameters = set(inspect.signature(plan_maintenance).parameters)
        assert parameters == {"rng", "spec", "assets", "practice"}
        forbidden = {"attack", "attacks", "scenario", "scenarios", "windows", "intervals"}
        assert not (parameters & forbidden)

    def test_the_realism_generator_cannot_see_an_attack(self) -> None:
        """The same structural refusal for the benign generator.

        ``start`` and ``duration`` rather than a ``spec``: the planner reads only those two fields
        of a run, and taking them directly is what keeps `phos.synth.realism` from importing
        `phos.synth.plant`, so the plant can import the planner and apply its effects where
        readings are made. The refusal this test exists for is unchanged and is now asserted the
        same way the maintenance planner's is.
        """
        parameters = set(inspect.signature(plan_realism).parameters)
        assert parameters == {"rng", "start", "duration", "profile", "spans"}
        forbidden = {"attack", "attacks", "scenario", "scenarios", "windows", "intervals"}
        assert not (parameters & forbidden)

    def test_neither_independent_generator_imports_the_scenario_catalogue(self) -> None:
        """Structural independence: they could not consult the attacks even if asked to."""
        for name in ("maintenance.py", "realism.py"):
            tree = ast.parse((GENERATOR_ROOT / name).read_text(encoding="utf-8"))
            modules = [module for module, _ in imported_targets(tree)]
            assert "phos.synth.scenarios" not in modules
            assert "phos.synth.catalogue_scenarios" not in modules


class TestTwoAttacksAreSpecifiedByIntent:
    """Mechanism 2. A goal in the plant's terms, never a quantity the detector computes."""

    def test_no_scenario_names_anything_atlas_exports(self) -> None:
        """The forbidden lexicon is Atlas's own surface, so it widens as Atlas does."""
        exported = {
            name.lower()
            for name in atlas_packet.__all__
            if (len(name) > 6 and name.upper() == name) or name.islower()
        }
        offences = [
            (scenario.scenario_id, name)
            for scenario in SCENARIOS
            for name in exported
            if name in scenario.prose().lower()
        ]
        assert offences == []

    def test_no_scenario_uses_the_vocabulary_of_detection(self) -> None:
        offences = [
            (scenario.scenario_id, word)
            for scenario in SCENARIOS
            for word in DETECTION_CONCEPTS
            if word in scenario.prose().lower()
        ]
        assert offences == []

    def test_a_goal_names_a_signal_the_plant_declares(self) -> None:
        """The goal's reach is a plant signal, which is the only vocabulary available to it."""
        assert all(
            scenario.goal.signal.endswith(("_m", "_mgpl", "_bar", "_mw", "_kv"))
            for scenario in SCENARIOS
        )

    def test_difficulty_is_carried_by_patience_not_by_a_magnitude(self) -> None:
        """There is no field on a scenario for how large a departure to produce."""
        fields = set(Scenario.model_fields)
        assert "patience_steps" in fields
        for forbidden in ("magnitude", "deviation", "strength", "subtlety", "sigma", "z_score"):
            assert forbidden not in fields

    def test_scenarios_span_both_patient_and_impatient_adversaries(self) -> None:
        patience = [scenario.patience_steps for scenario in SCENARIOS]
        assert min(patience) == 1
        assert max(patience) > 1000


class TestThreeEveryScenarioCarriesProvenance:
    """Mechanism 3. The shape came from the world, and the citation says where."""

    def test_the_catalogue_is_not_empty(self) -> None:
        assert len(SCENARIOS) >= 8

    def test_every_scenario_cites_a_real_world_source(self) -> None:
        for scenario in SCENARIOS:
            assert isinstance(scenario.provenance.kind, ProvenanceKind)
            assert len(scenario.provenance.citation) > 30, scenario.scenario_id
            assert len(scenario.provenance.shape) > 30, scenario.scenario_id

    def test_the_catalogue_draws_on_more_than_one_kind_of_source(self) -> None:
        assert len({scenario.provenance.kind for scenario in SCENARIOS}) >= 3

    def test_a_scenario_justified_by_our_own_detector_is_refused(self) -> None:
        """The forbidden justification, refused at the point of definition."""
        with pytest.raises(ValueError, match="placeholder or as a statement about our own"):
            Provenance(
                kind=ProvenanceKind.ATTACK_TAXONOMY,
                citation="this would be interesting for Atlas to catch",
                shape="something that moves a lot of signals at once",
            )

    def test_a_placeholder_citation_is_refused(self) -> None:
        with pytest.raises(ValueError, match="placeholder"):
            Provenance(
                kind=ProvenanceKind.ATTACK_TAXONOMY,
                citation="TBD — fill this in later please",
                shape="something that moves a lot of signals at once",
            )

    def test_the_batch_reactor_has_no_scenarios(self) -> None:
        """It declares no control network. Command attacks there would be fiction."""
        assert scenarios_for("batch-reactor") == ()


class TestFourTheBandThatMustBeMissed:
    """Mechanism 4. A generator producing only catchable attacks is a mirror."""

    def test_the_catalogue_contains_attacks_below_any_plausible_floor(self) -> None:
        """Patient adversaries whose per-step change is far under the plant's own variation."""
        below_floor = [scenario for scenario in SCENARIOS if scenario.patience_steps >= 720]
        assert below_floor, (
            "every scenario in the catalogue is one a detector could plausibly catch, which "
            "makes this generator a mirror of the detector rather than a test of it"
        )

    def test_at_least_one_scenario_stays_inside_the_plants_normal_range(self) -> None:
        """Not merely slow: an end point an operator could have dialled in legitimately."""
        constrained = [
            scenario
            for scenario in SCENARIOS
            if any(
                "inside" in c or "under the swing" in c or "ordinary" in c
                for c in scenario.goal.constraints
            )
        ]
        assert constrained

    def test_a_realism_run_produces_benign_cases_that_would_tempt_a_detector(self) -> None:
        plan = plan_realism(
            numpy.random.default_rng(3),
            _spec().start,
            _spec().duration,
            RealismProfile(
                grade_changes=2,
                sensor_faults=3,
                comms_dropouts=2,
                operator_interventions=2,
                startup_transitions=1,
                ageing_signals=("level_m",),
            ),
            {"level_m": (0.0, 6.0)},
        )
        assert plan.attack_like(), (
            "a benign class with no hard cases cannot support a false-positive figure worth "
            "quoting; this run produced none"
        )
        assert len(plan.attack_like()) >= 5

    def test_the_benign_phenomena_span_the_kinds_that_actually_confuse(self) -> None:
        plan = plan_realism(
            numpy.random.default_rng(3),
            _spec().start,
            _spec().duration,
            RealismProfile(
                grade_changes=2,
                sensor_faults=3,
                comms_dropouts=2,
                operator_interventions=2,
                startup_transitions=1,
            ),
            {"level_m": (0.0, 6.0)},
        )
        kinds = {item.kind for item in plan.phenomena}
        assert {
            PhenomenonKind.GRADE_CHANGE,
            PhenomenonKind.SENSOR_FAULT,
            PhenomenonKind.COMMS_DROPOUT,
            PhenomenonKind.OPERATOR_INTERVENTION,
            PhenomenonKind.STARTUP_TRANSITION,
        } <= kinds

    def test_a_quiet_profile_produces_nothing_at_all(self) -> None:
        """The additive property: realism off means byte-identical to before this existed."""
        plan = plan_realism(
            numpy.random.default_rng(3),
            _spec().start,
            _spec().duration,
            RealismProfile(),
            {"level_m": (0.0, 6.0)},
        )
        assert plan.phenomena == ()
        assert plan.attack_like() == ()

    def test_the_maintenance_calendar_produces_uncovered_and_covered_time(self) -> None:
        """Both halves must exist or the CMMS join has nothing to be exercised on."""
        register = plan_maintenance(
            numpy.random.default_rng(5),
            _spec(days=180),
            ("intake", "dosing", "clearwell"),
            MaintenancePractice(),
        )
        assert register.sanctioning(), "no order sanctions anything, so nothing is ever covered"
        assert len(register.sanctioning()) < len(register.orders), (
            "every order sanctions, so the refusal that a cancelled order covers nothing is "
            "never exercised by data"
        )


class TestFiveTheMethodIsPublishedIncludingItsFailures:
    """Mechanism 5. The limitations section is a required deliverable, not an afterthought."""

    def test_the_method_document_exists(self) -> None:
        assert METHOD_DOC.is_file(), f"{METHOD_DOC} is a required deliverable"

    @pytest.mark.parametrize(
        "heading",
        [
            "## What this is, and what it is not",
            "## The anti-bias construction",
            "## What the synthetic data probably gets wrong",
            "## What no result here may be used for",
        ],
    )
    def test_the_method_document_carries_its_required_sections(self, heading: str) -> None:
        assert heading in METHOD_DOC.read_text(encoding="utf-8")

    def test_the_limitations_section_is_substantial(self) -> None:
        """A one-line "it is synthetic" is not the honest limitations section that was asked for."""
        text = METHOD_DOC.read_text(encoding="utf-8")
        start = text.index("## What the synthetic data probably gets wrong")
        end = text.index("## What no result here may be used for")
        assert len(text[start:end].split()) > 400


def _spec(days: int = 30) -> RunSpec:
    """A minute-sampled run of ``days`` days, for the generators that need one."""
    return RunSpec(
        seed=1,
        start=datetime(2026, 3, 1, tzinfo=UTC),
        duration=timedelta(days=days),
        sample_interval=timedelta(minutes=1),
    )
