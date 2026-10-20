# Lane C — evidence-grade reports

## What was built

`src/phos/reasoning/reports.py` turns one stored narrative into a report. It does not detect, and
it does not score a corpus. Each sentence quotes a field the store already holds: the evidence
summary, time, kind, and entities; the hypothesis label and template id; whether that evidence is
listed as supporting or contradictory; and, on the 72-hour stages, the source, the facet, and any
causal edge. The evidence id is in the sentence.

The ontology has no incident-type enum. The incident type is the template id on each hypothesis
the narrative stores. `insufficient_evidence` has to be one of those hypotheses, or the builder
refuses the report. A narrative with no evidence is refused too, because there is no id to cite.

The narrative title and the entity's display name stay off the page. They are not evidence ids.

## Which incident types render

The tests render every template id the current libraries register:

| Template id | Stored label |
| --- | --- |
| `sensor_or_device_fault` | A sensor or device on this unit has failed |
| `engineering_maintenance` | A planned engineering or maintenance change |
| `process_disturbance` | A real process upset on this unit |
| `unauthorised_control_activity` | Unauthorised control activity on this unit |
| `benign_role_change` | A sanctioned change in this person's role or work |
| `peer_anomaly` | Behaviour unlike this person's declared peer group |
| `compromised_account` | This account is being used by someone other than its owner |
| `insider_misuse` | The account holder is misusing the access they hold |
| `generic_anomalous_activity` | Anomalous activity of unknown cause (generic) |
| `generic_benign_change` | Benign change to the environment (generic) |
| `insufficient_evidence` | Insufficient evidence to explain this behaviour |

The two `generic_*` ids are the PART 4B placeholders. They render under the label the template
stores. That label is not an Atlas or Sentiel finding.

## Stages

Each report has four blocks:

- NIS2 early warning, 24 hours
- NIS2 incident notification, 72 hours
- UK initial notification, 24 hours
- UK full notification, 72 hours

The 72-hour text starts with the 24-hour sentences and adds source, facet, and causal edges. The
UK block on a clock uses the same sentences as the NIS2 block on that clock.

`unlawful_or_malicious_suspected` is `not_asserted`. Cross-border impact is `not_in_store`.
Severity, impact, and indicators of compromise are `not_this_stage` at 24 hours and `not_in_store`
at 72 hours. Hypothesis confidence, the prior, and `overall_confidence` stay off the page even
when a narrative has `overall_confidence` set. The fixed fields are `confidence_surfaced=false`
and `overall_confidence=withheld`.

## Checker

The checker fails closed. `check_sentence` rejects a sentence with no evidence id.
`check_rendered_report` rejects a rendered report if any sentence lacks an evidence id the store
holds for that narrative, if `insufficient_evidence` is missing from a stage, or if a stored
confidence number appears. Header lines are a fixed allowlist, so a prose claim cannot hide in
metadata. The tests cover a sentence with no evidence id, an unknown id, a malice prompt filled
in as `yes`, a surfaced confidence of 0.137, and all eleven template ids above.

## What limited this lane

The module is in place. Two limits are written down rather than filled with a guess.

The UK stage names follow the v1 roadmap and the 12 November 2025 announcement of the Cyber
Security and Resilience Bill: an initial notification within 24 hours and a fuller report within
72 hours. This session did not read an enacted instrument. `legislation.gov.uk` is not a host the
October build may fetch. No UK content schedule was invented. The NIS2 one-month final report and
an MSP customer notice are outside this module; ADR 0157 says why.

Lane rules leave `PROGRESS.md`, `README.md`, `docs/adr/README.md`, the encyclopedia, and the
easy-to-reads for the merge. ADR 0158 and ADR 0159 were not used. No corpus was opened or scored.
