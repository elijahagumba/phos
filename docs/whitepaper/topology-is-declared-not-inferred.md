# Grouping answers "one event or ten?" Membership is not allowed to answer it with the same statistic that raised the alarm.

When a pump falters, every instrument on it moves. A joint model that attributes the break back to each breaking signal then emits one deviation per instrument. Ten sensors, ten things to investigate, one physical event. `group_evidence` in `src/phos/atlas/grouping.py` is the collapse. `SubsystemMap` in `src/phos/atlas/topology.py` is the only legal source of which signals share a unit. ADR 0010 is the decision. The shortcut that clusters signals by co-movement is rejected in the module docstring, and the constructor is written so the shortcut cannot sneak in as a partial map.

## Why a correlation cluster is circular

Grouping exists to decide whether deviations shared a cause. If the groups were themselves the output of "these signals moved together in training", then moving together would be both the reason they are one group and the evidence that the group is one event. The log would show fewer alerts. The plant would not have been consulted. A subsystem whose `source` string read "clustered by correlation" would be visibly the wrong kind of document. `source` is a required non-blank field for that reason. It is the audit path, not a caption.

The same circularity is why command evidence is not passed through `group_evidence`. A `SubsystemMap` partitions signals. It says nothing about devices on a network. Deriving a device group from co-occurrence would be the circularity `topology.py` already refuses. `UNGROUPED_COMMAND_EVIDENCE_CAVEAT` is that omission stated as a caveat rather than left as a bug.

## Construction fails closed

`SubsystemMap.__init__` takes the declared units and the corpus signal keys. It raises `TopologyError` for all of the following, and there is no mutation API afterward:

- two subsystems share an identifier
- a subsystem has no signals
- a signal is assigned twice
- a declared signal is not in the corpus
- a corpus signal is unassigned

A partial map is worse than no map. The unmapped remainder would fall back to per-signal counting, the failure would look like a quieter queue, and nobody would see the hole. All four coverage failures are unrecoverable at runtime because they are refused at construction. `SCHEMA_VERSION` is `1`. A file with any other version is refused rather than read optimistically. A topology read half-correctly is a partition that is quietly wrong.

`subsystem_for` is total on the corpus it was built against. A signal from a different corpus raises. Guessing a unit there would corrupt every count taken from the map, and the corruption would look like a result.

## What the collapse does, and what it refuses to do

`group_evidence(evidence, subsystem_map, window, deviations)` is a pure function. Same arguments, same events, same order. A non-positive `window` raises. A zero window would put every fact in its own event and collapse nothing, which is a silent no-op dressed as a call.

The group key is `(domain, subsystem_id, window start)`. Domain is in the key so two engines' evidence cannot land in one event by sharing a clock. That would be cross-engine correlation, which this module does not do. The window grid is anchored to `datetime(1970, 1, 1, tzinfo=UTC)`, not to the first timestamp in the batch. Two runs over overlapping slices agree about which bucket a measurement fell in. The cost is the ordinary tumbling-window cost: two departures a second apart land in different events if they straddle a boundary.

The signal is not read off `Evidence.entity_ids`. In a CSV corpus every signal is attributed to one entity, so the entity cannot say which column moved. `_signal_of` walks `source_id` to the `Deviation` and reads `deviation.expected.feature`. A missing deviation raises. Inventing a signal there would assign a unit.

The representative event:

- kind `DEVIATION`
- `source_id` = `subsystem-event:` plus the member evidence ids, earliest first, comma-separated
- `entity_ids` = the distinct signals, sorted
- timestamp = the earliest member
- `weight` = the max member weight, ties broken by signal name
- summary names the unit, the count of signals that departed, the size of the unit, and the strongest signal

`member_evidence_ids` is the only reader of that prefix. Called on a per-signal fact it raises, because returning that fact's `source_id` would hand back a deviation id and call it a member list. Nothing is discarded. Every input lands in exactly one event. `tests/atlas/test_grouping.py` asserts the count and the coverage separately. A counting change that drops a member is a filter, and this function is not a filter.

The weight rule is the dishonest one if you read it as a probability. `GROUPED_WEIGHT_CAVEAT` in `src/phos/atlas/engine.py`: a maximum of calibrated probabilities is not a calibrated probability. It is biased upward by how many signals the unit carries. The calibration error reported on subsystem events is therefore not a reading of the calibrator.

`AtlasEngine.run` groups before it reasons. Reasoning first would count one pump once per instrument, and every confidence downstream would scale with the size of the instrumentation. That order is the point of the vertical. The engine owns no detector and no belief arithmetic. It calls the pieces in this order.

## The number, and the caveat that has to travel with it

On HAI, 5,123 per-signal alerts became 424 subsystem events. That is the 12.1× counting reduction in the package docstring of `src/phos/atlas/__init__.py`, with both attack windows still covered. The frozen grouped row is `atlas-vertical:atlas-mahalanobis+isotonic/subsystem-events`: 53.26 false positives per normal hour, window recall 1.00, 424 alerts over 7.89 normal hours, of which 6 overlap a labelled attack. The ungated Mahalanobis cell on the same corpus is 646.58 false positives per normal hour. Those log names stay.

`COARSE_MAP_CAVEAT`: HAI's declared topology could not be partitioned below process level, so unrelated departures anywhere on one process collapse into a single subsystem event. A large reduction is evidence that grouping is implemented. It is not evidence that the units are correctly resolved. A finer map would lower the headline and raise its meaning.

`CO_OCCURRING_FAULT_MASKING_CAVEAT` is the other edge of the same knife. Two independent faults on one process are indistinguishable from one. An attack that co-occurs with a fault is reported as a single thing to investigate. That is a recall risk carried by the grouping. It is not a win.

A later attempt to spend a learned plant map on detection failed its gate (ADR 0143). The map had caught falsified sensors on simulated plants. Taken once to the HAI editions, it caught fewer attacks than the frozen detector on two of them and more on none, so it was not adopted. Simulated plants remain a diagnosis. ADR 0143 forbids quoting them as an improvement on real plant data.

## What would reverse the module

Inferring membership from co-movement, from name similarity, or from a blank `source`. Letting an unassigned signal through. Grouping command evidence with a signal map. Re-scoring inside `group_evidence`. Reading the 12.1× as a detection improvement rather than a change in what is counted. Retuning the grouped row to overwrite 53.26 or 646.58.
