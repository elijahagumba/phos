"""The scenarios themselves: what each adversary wants, and where in the world that shape is from.

Each entry below is a goal in the plant's own language plus a citation. Read the citations first —
they are the argument that these are attacks somebody has actually seen or that the process
engineering says are actually possible, rather than attacks chosen because we can catch them.

The two plants that have a control network get scenarios; the batch reactor deliberately has none,
because it declares no control network and inventing one there would be fiction (ADR 0015, and the
encyclopedia's note that expanding command attacks onto it would be exactly that).

**The band that must be missed.** Some of these are written to be beyond any plausible detector,
and they stay in the catalogue for that reason. A patient adversary walking a setpoint a few
hundredths at a time inside its normal operating range is not distinguishable from a plant having
a slightly unusual week, and a generator that only produced catchable attacks would be a mirror.
`tests/synth/test_anti_bias.py` fails if a run produces none of them.
"""

from typing import Final

from phos.synth.scenarios import (
    Direction,
    PhysicalGoal,
    Provenance,
    ProvenanceKind,
    Scenario,
)

__all__ = ["SCENARIOS", "scenarios_for"]

_INDUSTROYER: Final = Provenance(
    kind=ProvenanceKind.DOCUMENTED_INCIDENT,
    citation=(
        "ESET, 'Industroyer: Biggest threat to industrial control systems since Stuxnet' (2017), "
        "and Dragos, 'CRASHOVERRIDE: Analysis of the Threat to Electric Grid Operations' (2017)"
    ),
    shape=(
        "An adversary issuing ordinary, well-formed control-protocol writes from a host inside "
        "the control network, using the protocol as designed rather than exploiting it"
    ),
)

_STUXNET: Final = Provenance(
    kind=ProvenanceKind.DOCUMENTED_INCIDENT,
    citation=(
        "Falliere, Murchu and Chien, 'W32.Stuxnet Dossier', Symantec Security Response v1.4 "
        "(2011), on falsified process reporting during manipulation"
    ),
    shape=(
        "Driving the process away from its safe operating point while what the operators are "
        "shown continues to look ordinary"
    ),
)

_OLDSMAR: Final = Provenance(
    kind=ProvenanceKind.DOCUMENTED_INCIDENT,
    citation=(
        "Pinellas County Sheriff's Office briefing and the joint CISA/FBI/EPA advisory AA21-042A "
        "(2021), on the remote alteration of a water treatment chemical setpoint"
    ),
    shape=(
        "A single large setpoint change to a dosing parameter, made quickly from an operator "
        "station and reversible by hand"
    ),
)

_MITRE_ICS: Final = Provenance(
    kind=ProvenanceKind.ATTACK_TAXONOMY,
    citation=(
        "MITRE ATT&CK for ICS, techniques T0836 'Modify Parameter' and T0831 'Manipulation of "
        "Control'"
    ),
    shape=(
        "Changing a controller's operating parameter through the normal command path so the "
        "loop itself carries the process to the adversary's operating point"
    ),
)

_CLEARWELL_OVERFLOW: Final = Provenance(
    kind=ProvenanceKind.PROCESS_FAILURE_MODE,
    citation=(
        "Conventional surface-water treatment practice: a clearwell driven above its weir "
        "overflows to waste, and driven low breaks the chlorine contact time the disinfection "
        "credit depends on"
    ),
    shape=(
        "A level target walked slowly outside the range the works is operated within, so the "
        "loop does the damage over hours rather than the adversary doing it at once"
    ),
)

_GOVERNOR_ADVISORY: Final = Provenance(
    kind=ProvenanceKind.VENDOR_ADVISORY,
    citation=(
        "CISA ICS advisories on unauthenticated write access to generator and governor control "
        "parameters over Modbus/TCP, e.g. ICSA-15-062-01 class findings on unauthenticated "
        "function-code 6/16 writes"
    ),
    shape=(
        "An unauthenticated write to a dispatch or excitation parameter, indistinguishable at "
        "the protocol level from a legitimate one"
    ),
)

SCENARIOS: Final = (
    Scenario(
        scenario_id="wt-clearwell-overfill-impatient",
        plant_id="water-treatment",
        goal=PhysicalGoal(
            narrative=(
                "Drive the clearwell above the level the works is operated to, in one move, so "
                "the treated water overflows to waste"
            ),
            signal="clearwell_level_setpoint_m",
            direction=Direction.RAISE,
            limit=5.4,
            constraints=("Use the ordinary write path so the change looks like an operator's",),
        ),
        provenance=_OLDSMAR,
        issuer="scada",
        asset_id="clearwell",
        patience_steps=1,
        first_step=900,
    ),
    Scenario(
        scenario_id="wt-clearwell-overfill-patient",
        plant_id="water-treatment",
        goal=PhysicalGoal(
            narrative=(
                "Reach the same overfilled clearwell, but walk the level target there across "
                "several hours so no single change is larger than one an operator makes"
            ),
            signal="clearwell_level_setpoint_m",
            direction=Direction.RAISE,
            limit=5.4,
            constraints=(
                "No single step larger than a routine operator adjustment",
                "Keep the works inside its ordinary rhythm while the level walks",
            ),
        ),
        provenance=_CLEARWELL_OVERFLOW,
        issuer="scada",
        asset_id="clearwell",
        patience_steps=360,
        first_step=900,
    ),
    Scenario(
        scenario_id="wt-contact-time-erosion",
        plant_id="water-treatment",
        goal=PhysicalGoal(
            narrative=(
                "Lower the clearwell level far enough to erode the chlorine contact time the "
                "disinfection credit depends on, without leaving the range the works runs in"
            ),
            signal="clearwell_level_setpoint_m",
            direction=Direction.LOWER,
            limit=2.55,
            constraints=(
                "Stay inside the level range the works is operated within",
                "Move slowly enough to look like a seasonal change in operating practice",
            ),
        ),
        provenance=_CLEARWELL_OVERFLOW,
        issuer="engineering",
        asset_id="clearwell",
        patience_steps=720,
        first_step=1200,
    ),
    Scenario(
        scenario_id="wt-residual-suppression",
        plant_id="water-treatment",
        goal=PhysicalGoal(
            narrative=(
                "Suppress the chlorine residual target so treated water leaves the works "
                "under-disinfected"
            ),
            signal="chlorine_residual_setpoint_mgpl",
            direction=Direction.LOWER,
            limit=0.35,
            constraints=("Make the change from a station that already talks to this PLC",),
        ),
        provenance=_OLDSMAR,
        issuer="scada",
        asset_id="clearwell",
        patience_steps=30,
        first_step=1500,
    ),
    Scenario(
        scenario_id="wt-residual-drift-below-floor",
        plant_id="water-treatment",
        goal=PhysicalGoal(
            narrative=(
                "Move the residual target by less than the works' own week-to-week variation, "
                "and leave it there — an adversary content with a small permanent change"
            ),
            signal="chlorine_residual_setpoint_mgpl",
            direction=Direction.LOWER,
            limit=0.92,
            constraints=(
                "Change nothing by more than the plant's own ordinary variation",
                "Accept a small effect in exchange for being unremarkable",
            ),
        ),
        provenance=_MITRE_ICS,
        issuer="hmi",
        asset_id="clearwell",
        patience_steps=1440,
        first_step=600,
    ),
    Scenario(
        scenario_id="wt-pressure-transient",
        plant_id="water-treatment",
        goal=PhysicalGoal(
            narrative=(
                "Raise the distribution pressure target sharply enough to stress the network's "
                "older mains"
            ),
            signal="distribution_pressure_setpoint_bar",
            direction=Direction.RAISE,
            limit=6.2,
            constraints=("Act from a workstation that has never commanded this PLC",),
        ),
        provenance=_INDUSTROYER,
        issuer="engineering",
        asset_id="distribution",
        patience_steps=4,
        first_step=2100,
    ),
    Scenario(
        scenario_id="wt-quiet-pressure-creep",
        plant_id="water-treatment",
        goal=PhysicalGoal(
            narrative=(
                "Creep the distribution pressure target upward slowly enough that the change is "
                "smaller than the daily demand swing already moves the network"
            ),
            signal="distribution_pressure_setpoint_bar",
            direction=Direction.RAISE,
            limit=4.35,
            constraints=(
                "Stay under the swing the diurnal demand already produces",
                "Take as long as necessary",
            ),
        ),
        provenance=_STUXNET,
        issuer="hmi",
        asset_id="distribution",
        patience_steps=2880,
        first_step=300,
    ),
    Scenario(
        scenario_id="pg-dispatch-runback",
        plant_id="power-generation",
        goal=PhysicalGoal(
            narrative=(
                "Run the machine's dispatch target down hard, shedding real power the feeder is "
                "relying on"
            ),
            signal="dispatch_setpoint_mw",
            direction=Direction.LOWER,
            limit=2.0,
            constraints=("Use ordinary writes from inside the station network",),
        ),
        provenance=_INDUSTROYER,
        issuer="engineering",
        asset_id="generator",
        patience_steps=2,
        first_step=3000,
    ),
    Scenario(
        scenario_id="pg-excitation-push",
        plant_id="power-generation",
        goal=PhysicalGoal(
            narrative=(
                "Push the feeder voltage target above the band the station is licensed to hold "
                "it within"
            ),
            signal="feeder_voltage_setpoint_kv",
            direction=Direction.RAISE,
            limit=11.9,
            constraints=("Write the parameter directly rather than tripping anything",),
        ),
        provenance=_GOVERNOR_ADVISORY,
        issuer="scada",
        asset_id="feeder",
        patience_steps=6,
        first_step=2400,
    ),
    Scenario(
        scenario_id="pg-dispatch-shading-below-floor",
        plant_id="power-generation",
        goal=PhysicalGoal(
            narrative=(
                "Shade the dispatch target down by less than the station's own load-following "
                "movement, and hold it there"
            ),
            signal="dispatch_setpoint_mw",
            direction=Direction.LOWER,
            limit=7.4,
            constraints=(
                "Stay inside the movement the station already makes following load",
                "Prefer a small permanent shortfall to a visible one",
            ),
        ),
        provenance=_MITRE_ICS,
        issuer="hmi",
        asset_id="generator",
        patience_steps=2400,
        first_step=600,
    ),
)
"""Every scenario, across both networked plants. The batch reactor has none, by construction."""


def scenarios_for(plant_id: str) -> tuple[Scenario, ...]:
    """Return the scenarios written against one plant, in catalogue order."""
    return tuple(item for item in SCENARIOS if item.plant_id == plant_id)
