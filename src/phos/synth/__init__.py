"""The synthetic industrial data engine: plants we fully control, and ground truth we can trust.

Atlas's deepest constraint is not modelling. It is that clean, richly labelled, attack-dense
industrial data barely exists in public — HAI and BATADAL between them offer a handful of labelled
windows on two testbeds, and neither says *which explanation was true*, which is the thing a
reasoning engine most needs to be measured against. This subpackage is the answer to that: an
environment we build ourselves, understand completely, and can generate ground truth for.

D1 builds the environment and nothing else. Three simulated plants that produce labelled-as-normal
operation in both forms Atlas consumes, plus the two hooks the rest of the engine needs:

- **The injection hook** (`injection`) — the door D2's attacks come through, designed so that a
  manipulated run is separable from a normal one by the manipulation and by nothing else.
- **The true-state record** (`plant`) — what the plant is actually doing, recorded at every step
  independently of what its instruments report, so that D2's fabricated telemetry can be labelled
  honestly rather than reconstructed after the fact.

**How it fits Atlas.** Telemetry leaves through `phos.eval.Dataset` and the prepared-CSV shape
`phos.eval.LabelledCsvAdapter` already reads; topology leaves as the TOML
`phos.atlas.topology.load_topology` already reads; control traffic leaves as a pcap
`phos.atlas.packet.dissect_capture` already reads. Nothing in Atlas was changed to accept any of
it, and nothing here imports Atlas except the topology types it renders — which is what "no
special-casing" has to mean if it is to mean anything.

**Realism is the deliverable, not volume.** Each plant integrates what a real one integrates, lags
what a real one lags, and is controlled by loops acting on what its instruments report rather than
on the truth. Each carries measurement noise, calibration drift, cyclic and shift-based patterns,
and legitimate operational events — setpoint changes, backwashes, load steps, batch changeovers —
because a plant whose only sharp change is an attack is a plant detection is trivial in and which
does not exist.

**The standing caveat, stated here and carried in every dataset, manifest and topology this
package writes:** a plant we build is a model of reality, not reality. Its realism is a claim to
be defended — `PlantDescription.model_source` is where each plant defends it — and not a property
to be assumed. Good Atlas results on this data will mean Atlas handles *our model of a plant*: a
necessary step toward handling a real one, and not evidence of it. See `MODEL_NOT_REALITY_CAVEAT`.

**What is not here, deliberately.** No attacks and no use of the injection hook to attack anything
(D2). No evaluation of Atlas against any of it (D3). No modification of any existing module.
"""

from phos.synth.catalogue import CONFIG_SUFFIX, DatasetConfig, load_config, load_configs
from phos.synth.generate import (
    CAPTURE_FILE,
    MANIFEST_FILE,
    TELEMETRY_FILE,
    TOPOLOGY_FILE,
    GenerationError,
    generate_dataset,
)
from phos.synth.injection import (
    CompositeInjection,
    HoldActuator,
    HoldReading,
    Injection,
    NoInjection,
    TimeWindow,
)
from phos.synth.manifest import (
    MANIFEST_SCHEMA_VERSION,
    GeneratedFile,
    SynthManifest,
    build_manifest,
    digest_of,
    write_manifest,
)
from phos.synth.plant import (
    MODEL_NOT_REALITY_CAVEAT,
    BenignEvent,
    CommandIntent,
    CommandKind,
    ControlNetwork,
    Coupling,
    CouplingKind,
    EventPlan,
    NetworkNode,
    PhysicalUnit,
    Plant,
    PlantDescription,
    PlantStep,
    RegisterBlock,
    RunSpec,
    SensorReport,
    SignalKind,
    SignalSpec,
    TrueState,
    lay_out_events,
    register_count,
)
from phos.synth.plants import BatchReactorPlant, PowerGenerationPlant, WaterTreatmentPlant
from phos.synth.run import PLANT_FACTORIES, PLANT_IDS, PlantRun, build_plant, run_plant
from phos.synth.telemetry import (
    LABEL_COLUMN,
    NORMAL_LABEL,
    TIMESTAMP_COLUMN,
    SyntheticPlantAdapter,
    entity_id,
    observations,
    source_note,
    to_dataset,
    write_csv,
)
from phos.synth.topology import (
    SYNTHETIC_TOPOLOGY_CAVEAT,
    subsystem_map,
    subsystems,
    topology_toml,
    write_topology,
)
from phos.synth.traffic import MODBUS_PORT, TrafficPolicy, WireFrame, modbus_frames, write_pcap

__all__ = [
    "CAPTURE_FILE",
    "CONFIG_SUFFIX",
    "LABEL_COLUMN",
    "MANIFEST_FILE",
    "MANIFEST_SCHEMA_VERSION",
    "MODBUS_PORT",
    "MODEL_NOT_REALITY_CAVEAT",
    "NORMAL_LABEL",
    "PLANT_FACTORIES",
    "PLANT_IDS",
    "SYNTHETIC_TOPOLOGY_CAVEAT",
    "TELEMETRY_FILE",
    "TIMESTAMP_COLUMN",
    "TOPOLOGY_FILE",
    "BatchReactorPlant",
    "BenignEvent",
    "CommandIntent",
    "CommandKind",
    "CompositeInjection",
    "ControlNetwork",
    "Coupling",
    "CouplingKind",
    "DatasetConfig",
    "EventPlan",
    "GeneratedFile",
    "GenerationError",
    "HoldActuator",
    "HoldReading",
    "Injection",
    "NetworkNode",
    "NoInjection",
    "PhysicalUnit",
    "Plant",
    "PlantDescription",
    "PlantRun",
    "PlantStep",
    "PowerGenerationPlant",
    "RegisterBlock",
    "RunSpec",
    "SensorReport",
    "SignalKind",
    "SignalSpec",
    "SynthManifest",
    "SyntheticPlantAdapter",
    "TimeWindow",
    "TrafficPolicy",
    "TrueState",
    "WaterTreatmentPlant",
    "WireFrame",
    "build_manifest",
    "build_plant",
    "digest_of",
    "entity_id",
    "generate_dataset",
    "lay_out_events",
    "load_config",
    "load_configs",
    "modbus_frames",
    "observations",
    "register_count",
    "run_plant",
    "source_note",
    "subsystem_map",
    "subsystems",
    "to_dataset",
    "topology_toml",
    "write_csv",
    "write_manifest",
    "write_pcap",
    "write_topology",
]
