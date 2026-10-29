# One shared language

**What this is:** the shared chart that Atlas, Sentiel, and any future screen must all write on.

**Why it exists:** if each engine invents its own idea of an “alert,” you cannot compare them, you
cannot audit them, and a user interface would have to contain business logic. PHOS forbids that.

## Analogy: one hospital chart

In a hospital, the cardiology ward does not keep a private notebook that the rest of the building
cannot read. Heart rate, medication, and diagnosis go on **one chart**, with rules about who may
write what.

PHOS’s chart is called the **ontology**. The words are used everywhere, on purpose:

| Word | Everyday meaning |
| --- | --- |
| **Entity** | A thing being watched: a pump, a PLC, a person, a service |
| **Observation** | A measured fact at a time: “this sensor read 72.4 at 14:03” |
| **Baseline / expected range** | What “normal” looks like for that fact |
| **Deviation** | A reading outside that range, with a size |
| **Evidence** | A deviation (or a relationship change) attached to a story as *for* or *against* |
| **Hypothesis** | One candidate explanation, with a confidence that can move |
| **Narrative / incident** | The ordered story: evidence and competing explanations. Overall confidence stays unset until it is calibrated |
| **Causal edges** | Reconstructable “this finding bears on that explanation” arrows on the story. They are **not** a plant piping diagram. |

## Frozen facts, referenced by id

Once written, a record does not silently mutate. Later steps **point at it by id** rather than
copying a slightly different version. The store refuses a hypothesis that names evidence it has
never seen, the way a filing clerk refuses a folder that cites a missing lab result.

That is boring on purpose. Boring is what lets a displayed conclusion be **traced back**: narrative
→ hypothesis → evidence → deviation → observation. If you cannot walk that chain, the number is not
allowed on a screen. A narrative’s arrows must name evidence and hypotheses **already on that
story**; a silent poller that never shared a device with the command act does not get to argue
about it ([who belongs in the story](15-silence-stretch-and-who-belongs-in-the-story.md)).

## What this is not

- Not detection. The ontology does not decide what is an attack.
- Not a database product. The first store is in-memory, for tests and offline runs.
- Not a place for engine-private alert formats.

Forecasts (predicted future values) exist as types; they are not all stored yet. That is a known
gap, recorded in the original PART 1 log, not a hidden omission.

## Where to read more

- Code: `src/phos/ontology/`
- Decision: [ADR 0001](../docs/adr/0001-ontology-value-objects-and-store-enforced-integrity.md)
- Walked example in tests: an unexpected Modbus write, competing hypotheses, one timeline
