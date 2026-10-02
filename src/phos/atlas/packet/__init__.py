"""Atlas's packet adapter: industrial captures in, typed and traceable messages out.

Atlas until now has heard the plant's sensor *values* and been deaf to its *commands* — the
control traffic between engineering stations, PLCs and SCADA servers. That gap matters more than
it sounds: a tank level leaving its expected range says something is wrong, and only the command
stream can begin to separate an operator who opened a valve from an attacker who did. This
subpackage is where Atlas starts hearing them.

Import from here — ``from phos.atlas.packet import dissect_capture`` — rather than from the
submodules, so internal layout can change without breaking callers.

**The pipeline, in one line:** `dissect_capture` reads a capture lazily through `read_frames`,
peels each frame to its transport payload as a `RawFrame`, and hands it to the first
`ProtocolDissector` in a `DissectorRegistry` that claims it. Out comes an `IcsMessage` (today, a
`ModbusMessage`), an `UnparsedMessage` for traffic nobody claimed, or a `MalformedFrame` for
traffic a dissector claimed and then refused.

**What P1 is held to, beyond parsing correctly.**

- *Hostile input is contained by construction.* A parser inside a security product is itself an
  attack surface, and every byte here was chosen by whoever sent the frame. `modbus` checks before
  it reads and caps before it allocates, so it refuses rather than raises — with no `try` wrapping
  the decode to make that true. `tests/atlas/packet/test_hardening.py` fires thousands of random
  and mutated frames at the pipeline and asserts nothing escapes.
- *Coverage is measured, not assumed.* Traffic P1 cannot dissect becomes an `UnparsedMessage`;
  frames that never peel are counted in `CaptureStats`, whose four counters must sum to the frames
  read. A capture that yields nothing says why it yielded nothing.
- *Everything traces back.* Every message and every refusal carries a `FrameSource` naming the
  capture and the frame index, so a conclusion Atlas eventually draws can be walked back to a
  specific run of bytes in a specific file (Constitution §3.2).
- *One protocol, done properly.* Modbus/TCP is dissected; DNP3, S7comm and EtherNet/IP are not.
  The seam for them is `ProtocolDissector` plus a registry entry, and the tests prove it with a
  stub dissector for a protocol PHOS does not implement.

**What P2 adds on top.** P1 stops at "what does this frame say". P2 answers "is this normal", in
the only form that question has an answer: behaviour over time.

- `commands` normalises the message stream into `CommandEvent`s — who commanded whom, when — and
  is the one place that decides what a device *is* (its address) and what a command *is* (a
  request). `CommandStreamStats` keeps the coverage arithmetic honest one layer up from
  `CaptureStats`.
- `behaviour` turns those into per-device, per-window ontology `Observation`s — command volume and
  mix, write targets and values, read/write balance, and polling rhythm — so PART 3's baselines
  and 5A's joint models consume command behaviour through the path they already use for sensor
  telemetry, with no special case.
- `graph` learns which devices command which, and surfaces the three changes that are each
  potential evidence: a relationship never seen before, a learned one gone silent, and an
  unfamiliar function code on a known link.

**What P3 did with all of it.** `phos.atlas.command_evidence` promotes both streams through the
evidence boundary — behaviour through `evidence_from_deviation`, graph changes through P3's sibling
`evidence_from_relationship_change` — so command evidence reaches the reasoning engine as the same
object a sensor departure does. `AtlasEngine.run` takes the bundle alongside a corpus, and the OT
templates read a structural change as evidence *for* unauthorised control and *against* a process
upset, which is the separation process telemetry could never make. P3 also answered the question P2
left open about the two `phos.atlas.stability` stubs: they were **retired**, because
`COMMAND_INTERVAL_CV` and `UNEXPECTED_COMMAND_FUNCTION` carry those signals as observations that get
baselined, calibrated and measured, which a bare float never would.

**What none of it has established.** No command-level detection result exists. The pipeline is
proved in mechanism on hand-built fixtures; measuring it needs a capture containing a real
attacker's control action, labelled, and `phos.atlas.command_eval` is the seam waiting for one.
"""

from phos.atlas.packet.behaviour import (
    COMMAND_BASELINE_CAVEATS,
    COMMAND_COUNT,
    COMMAND_INTERVAL_CV,
    COMMAND_INTERVAL_MEAN_MS,
    DISTINCT_WRITE_ADDRESSES,
    FUNCTION_COUNT_PREFIX,
    REGISTER_WRITE_VALUE_MAX,
    REGISTER_WRITE_VALUE_MEAN,
    REGISTER_WRITE_VALUE_MIN,
    SHORT_CAPTURE_CAVEAT,
    UNREPRESENTATIVE_TRAFFIC_CAVEAT,
    WRITE_ADDRESS_MAX,
    WRITE_ADDRESS_MIN,
    WRITE_COMMAND_SHARE,
    CommandFeaturePolicy,
    featurise_commands,
    function_count_feature,
)
from phos.atlas.packet.capture import CaptureError, CaptureStats, read_frames
from phos.atlas.packet.commands import (
    REGISTER_WRITE_FUNCTIONS,
    WRITE_FUNCTIONS,
    CommandEvent,
    CommandStreamStats,
    Window,
    command_events,
    device_entity_id,
    is_register_write,
    is_write,
    stream_span,
    tile_windows,
)
from phos.atlas.packet.dissect import (
    DissectionResult,
    DissectorRegistry,
    ProtocolDissector,
    dissect_capture,
)
from phos.atlas.packet.frame import MAX_PORT, Endpoint, FrameSource, RawFrame, Transport
from phos.atlas.packet.graph import (
    SILENT_COMMAND_RELATIONSHIP,
    UNEXPECTED_COMMAND_FUNCTION,
    UNKNOWN_COMMAND_RELATIONSHIP,
    CommandEdge,
    DeviceCommandGraph,
    GraphComparePolicy,
    compare_to_graph,
    learn_device_command_graph,
    render_graph,
)
from phos.atlas.packet.messages import (
    MAX_REGISTER_VALUE,
    MODBUS_PROTOCOL,
    UNKNOWN_PROTOCOL,
    Direction,
    IcsMessage,
    MalformedFrame,
    MalformedReason,
    ModbusMessage,
    UnparsedMessage,
)
from phos.atlas.packet.modbus import (
    MAX_READ_COILS,
    MAX_READ_REGISTERS,
    MAX_WRITE_COILS,
    MAX_WRITE_REGISTERS,
    MBAP_HEADER_LENGTH,
    MODBUS_PORT,
    FunctionCode,
    ModbusDissector,
)

__all__ = [
    "COMMAND_BASELINE_CAVEATS",
    "COMMAND_COUNT",
    "COMMAND_INTERVAL_CV",
    "COMMAND_INTERVAL_MEAN_MS",
    "DISTINCT_WRITE_ADDRESSES",
    "FUNCTION_COUNT_PREFIX",
    "MAX_PORT",
    "MAX_READ_COILS",
    "MAX_READ_REGISTERS",
    "MAX_REGISTER_VALUE",
    "MAX_WRITE_COILS",
    "MAX_WRITE_REGISTERS",
    "MBAP_HEADER_LENGTH",
    "MODBUS_PORT",
    "MODBUS_PROTOCOL",
    "REGISTER_WRITE_FUNCTIONS",
    "REGISTER_WRITE_VALUE_MAX",
    "REGISTER_WRITE_VALUE_MEAN",
    "REGISTER_WRITE_VALUE_MIN",
    "SHORT_CAPTURE_CAVEAT",
    "SILENT_COMMAND_RELATIONSHIP",
    "UNEXPECTED_COMMAND_FUNCTION",
    "UNKNOWN_COMMAND_RELATIONSHIP",
    "UNKNOWN_PROTOCOL",
    "UNREPRESENTATIVE_TRAFFIC_CAVEAT",
    "WRITE_ADDRESS_MAX",
    "WRITE_ADDRESS_MIN",
    "WRITE_COMMAND_SHARE",
    "WRITE_FUNCTIONS",
    "CaptureError",
    "CaptureStats",
    "CommandEdge",
    "CommandEvent",
    "CommandFeaturePolicy",
    "CommandStreamStats",
    "DeviceCommandGraph",
    "Direction",
    "DissectionResult",
    "DissectorRegistry",
    "Endpoint",
    "FrameSource",
    "FunctionCode",
    "GraphComparePolicy",
    "IcsMessage",
    "MalformedFrame",
    "MalformedReason",
    "ModbusDissector",
    "ModbusMessage",
    "ProtocolDissector",
    "RawFrame",
    "Transport",
    "UnparsedMessage",
    "Window",
    "command_events",
    "compare_to_graph",
    "device_entity_id",
    "dissect_capture",
    "featurise_commands",
    "function_count_feature",
    "is_register_write",
    "is_write",
    "learn_device_command_graph",
    "read_frames",
    "render_graph",
    "stream_span",
    "tile_windows",
]
