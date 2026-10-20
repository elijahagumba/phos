# Lane T — the trusted station turned hostile

Simulated diagnosis. The synthetic command harness was built so its results cannot be believed as field rates (ADR 0073). Nothing here is a field rate, and nothing here is ≥70%.

Known-station and unknown-master stays are scored apart. They are not pooled.

## The limit, restated before any new check

| Issuer kind | Unique lead | Moved | n | Record |
| --- | ---: | ---: | ---: | --- |
| Known station (`scada` / `hmi`) | **0** | 6 | 16 | ADR 0034, remeasured ADR 0037 and ADR 0038 |
| Unknown master (silent `engineering`) | **1** | 4 | 4 | ADR 0037 and ADR 0038 |

The **1 of 4** is a D2 diagnostic with `ATTRIBUTION_RANK_IS_NOT_A_RATE_CAVEAT`. It is not detection, and it is not added to the **0 of 16**.

What fails on the known station: a write from a station the learned graph already trusts (`scada` or `hmi`) leaves `unexpected_command_function` or silence on a known link. That fact still supports both `engineering_maintenance` and `unauthorised_control_activity` (ADR 0014, ADR 0034). Maintenance's prior wins, or the two share the lead. A tie is a refusal (`tied_lead_ids`), not an alphabetical winner (ADR 0036). ADR 0039's ranking-contract tests stay the lock on undoing that.

This lane does not remeasure that battery, does not retune known-link matchers, and does not move `unexpected_command_function` or silent known-link off maintenance support.

The false-alarm figure this lane is held to is ADR 0086's: **0.20** (4 of 20) narratives per authorised run. A narrative that does not concern the authorised write counts. Silence is 0. Maintenance that is about that write is not a false alarm. The bar is not above 0.20.

## Seeds

Development **97801–97820** may be built in memory. Held-back **97901–97920** is not scored until a declaration commit names the command, the result name, the challenger sha256, and the bars. The issuer in every run is the plant's declared operator, a known station, never a silent engineering workstation.

## Hypotheses

### H1 — toward a limit, against the plant (declared, not yet run)

A write by the declared operator that moves a setpoint toward a declared safety limit (the signal's own low or high), and against the direction the reported state calls for, is evidence for `unauthorised_control_activity`. The called-for direction is the sign of setpoint minus the controlled measurement on the last sample before the write. A deadband of three times that measurement's own noise treats a smaller error as a hold; a move out of the plant's declared operating band during a hold is against the hold. The operating band is the range the plant already uses for ordinary operator writes, not a threshold searched on these seeds.

Authorised unusual writes in this batch go with that call, so they should not gain the fact. A covering work order withholds it as well. The fact is a command-effect, not a known-link function change. Weight is `FittedPlattCalibrator(coefficient=0.0, intercept=0.0)`, which is one half. It is not tuned.

Predicted on development seeds 97801–97820, one hostile write and one authorised run each, water-treatment, issuer `hmi`:

- The fact attaches on the hostile write and does not attach on the authorised run.
- One half-weight supporting fact lifts unauthorised from its prior 0.02 to about 0.034. The residual prior is 0.30, so the narrative lead stays `insufficient_evidence`. Unique unauthorised lead is predicted **0 of 20**. A tie would not count either.
- Authorised runs stay silent. False-alarm narratives per authorised run are predicted **0.00**, not above 0.20.
- `test_a_function_change_on_a_known_link_still_supports_both` and `test_a_silent_known_link_still_supports_both` stay green.

**Development result (HEAD `b3d2dd8`, `eval_runs/build/d/trusted/h1-development.md`).** The prediction held on all 20 seeds.

| | Hostile unique leads | Authorised facts | False alarms per authorised run |
| --- | ---: | ---: | ---: |
| H1 | **0 of 20** | 0 of 20 | **0.00** (0 of 20) |

Every hostile write gained the fact. The narrative lead was `insufficient_evidence` on every one of them, because one half-weight fact does not pass the residual prior. That is not a unique lead. Authorised runs stayed silent. H1 is kept as evidence. It is not, by itself, a challenger that meets the lead bar. Known-link both-support tests were green in the same commit.

### H2 — a jump, or a write outside the mode (declared, not yet run)

A setpoint change larger than the plant's declared operating-band width, or a write while a manual mode is in force (filter backwash or intake stop), supports `unauthorised_control_activity`. Same weight as H1. Not tuned.

The authorised run in this batch is itself a jump: 3.0 m to 4.5 m, and the band is 1.2 m wide. Predicted on 97801–97820:

- The jump fact attaches on the hostile write and on the authorised jump.
- Manual mode does not attach. The write is before the plant's first benign event.
- Each authorised run then has a narrative that is not maintenance about that write. False-alarm narratives per authorised run are predicted **1.00**, above 0.20.
- Unique unauthorised leads stay **0 of 20**. Two half-weight facts still sit under the residual prior.
- If the false-alarm rate is above 0.20, H2 is rejected and stays in this file.

**Development result (HEAD `c9d066e`, `eval_runs/build/d/trusted/h2-development.md`).** The prediction held. **H2 is rejected.**

| | Hostile unique leads | Authorised facts | False alarms per authorised run |
| --- | ---: | ---: | ---: |
| H2 | **0 of 20** | 1 of 20 on every seed | **1.00** (20 of 20) |

One fact per run. The write is before the plant's first benign event, so the manual-mode clause did not attach. The jump did, on the hostile write and on the authorised jump. 1.00 is above 0.20. The features stay in the code. They are not part of the challenger.

### H3 — write and hide (declared, not yet run)

The write coincides with the controlled measurement staying inside three of its own noise standard deviations while the actuator moves at least `MIN_RESPONSE_SHARE` of its span. That is the hide: operators cannot see the effect. It is a command-effect feature, `write_and_hide`, not `CROSS_SIGNAL_MISMATCH` and not a known-link function change. Same half weight. Horizon is 8 samples, so the window ends before the plant's first benign event. The threshold is not searched.

Hostile runs freeze the clearwell report at the last honest value from the write onward. Authorised runs do not.

Predicted on 97801–97820:

- The fact attaches on the hostile write and does not attach on the authorised run.
- False-alarm narratives per authorised run **0.00**, not above 0.20.
- Unique unauthorised leads **0 of 20**. One more half-weight fact still leaves the residual ahead. H1 and H3 together are two facts, still under the residual. The weight is not raised to change that.

**Development result (HEAD `f135d57`).** H3 is kept. It does not uniquely lead.

| | Hostile unique leads | Hostile facts | Authorised facts | False alarms per authorised run |
| --- | ---: | ---: | ---: | ---: |
| H3 | **0 of 20** | 1 of 20 on every seed | 0 of 20 | **0.00** (0 of 20) |
| H1+H3 | **0 of 20** | 2 of 20 on every seed | 0 of 20 | **0.00** (0 of 20) |

Reports: `h3-development.md`, `h1-h3-development.md`. The narrative lead was `insufficient_evidence` on every hostile seed. Two half-weight facts reach about 0.058, under the residual prior 0.30. H2 stays rejected. The challenger to freeze is H1+H3, features `toward_limit_against_state` and `write_and_hide`.

## Held-back declaration

ADR 0254 declares seeds 97901-97920, result name `trusted-station:known-operator-effect`, command `uv run python scripts/score_trusted_station.py --split held-back`, and challenger sha256 `981270a8c60a0d4733e739ae182a01af2e040b90a9786406c6b77cbaa718f747`.

## Held-back result

Scored once after `592d051`. Report: `eval_runs/build/d/trusted/held-back.md`. A second invocation was refused because the output exists. The file was not rewritten.

| Bar | Result | |
| --- | --- | --- |
| Hostile known-station writes led in more than 0 of them | **0 of 20** | **not met** |
| False-alarm narratives per authorised run not above 0.20 | **0.00** (0 of 20) | **met** |
| Known-link both-support tests green | 3 passed | **met** |

The lead bar is not met. It is not rerun and it is not reworded. Every hostile seed gained both facts and the narrative lead was `insufficient_evidence`. This is a simulated diagnosis. It is not a field rate (ADR 0073), not the frozen 0 of 16, and not ≥70%.
