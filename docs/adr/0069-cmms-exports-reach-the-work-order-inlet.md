# ADR 0069 — A maintenance system's own export reaches the work-order inlet

- **Status:** Accepted
- **Date:** 2026-08-26
- **PART:** Build 2 (CMMS join)
- **Supersedes:** nothing
- **Depends on:** [ADR 0027](0027-unknown-master-writes-are-not-maintenance.md),
  [ADR 0040](0040-no-labelled-public-command-corpus.md),
  [ADR 0059](0059-explanation-geometry-and-work-order-inlet.md),
  [ADR 0068](0068-the-atlas-operator-queue-cannot-be-ranked.md)

## Context

Session E3 ([ADR 0059](0059-explanation-geometry-and-work-order-inlet.md)) built the work-order
inlet and wired the templates: a `work-order:` stamped fact **supports** `engineering_maintenance`
and **contradicts** `unauthorised_control_activity`. That pairing is the only thing in Atlas that
separates a commissioning engineer from an attacker on a known station — the wall ADR 0027 and
the category roadmap both name as unclimbable on process telemetry alone.

E3 left no way to get a work order *in*. `promote_work_orders` takes `Sequence[Observation]`, so
every caller hand-built its facts and every test was a fixture. The inlet has never seen a real
maintenance record.

[ADR 0068](0068-the-atlas-operator-queue-cannot-be-ranked.md) sharpened why this matters. The
operator queue cannot be ranked by any severity Atlas carries: joint distance sorts the incidents
into the back half, calibrated weight is a constant, breadth takes four values. The candidate
severities that record named were persistence, cross-subsystem coincidence, and **the absence of a
covering work order** — and only the last is something a real plant already has and no public
corpus does.

## Decision

1. **`src/phos/atlas/cmms.py` reads a maintenance system's own export** into `WorkOrderRecord`s
   and then into the observations `promote_work_orders` already accepts. Two schemas ship,
   spelled with the systems' real field names: `SAP_PM_SCHEMA`
   (`AUFNR`/`EQUNR`/`GSTRP`/`GLTRP`/`STTXT`/`AUART`) and `MAXIMO_SCHEMA`
   (`WONUM`/`ASSETNUM`/`SCHEDSTART`/`SCHEDFINISH`/`STATUS`/`WORKTYPE`). A site that renames
   columns declares its own `CmmsSchema`.

2. **Columns and timestamp formats are declared, never sniffed.** A column guessed from its values
   is a window silently shifted, so a missing declared column and an unparseable timestamp are
   both refused by name.

3. **Missing is not empty.** `load_work_order_export` raises `CmmsExportMissingError` on an absent
   file rather than returning `()`. An empty export is the finding "no sanctioned change in this
   window" and may be reasoned from; a missing one is silence and must never read as a plant-wide
   alibi.

4. **Asset identity is exact and declared.** An order naming an asset outside the plant's declared
   set raises `UndeclaredAssetError` rather than being dropped — a silently discarded row makes
   every alert on that unit look unexplained while the file appears to load cleanly. `P-101` never
   covers `P-1010`; there is no prefix, substring or fuzzy match.

5. **Only a sanctioning status covers anything.** Statuses are declared per schema — Maximo
   `APPR`/`INPRG`/`COMP`, SAP `REL`/`TECO`. A cancelled Maximo order (`CAN`) and a SAP draft
   (`CRTD`) authorised nothing; they are excluded and counted in the log line, never silently
   treated as cover.

6. **A covering order is not innocence** (`WORK_ORDER_COVERAGE_IS_NOT_INNOCENCE`). It makes
   maintenance a live explanation weighed against the others with the losers still visible. An
   attacker holding the maintenance calendar can act inside a window, and a forged export is a
   forged export. Nothing here raises or lowers a detection score.

7. **No public corpus carries work orders, and that stays pinned.**
   `discover_work_order_exports` reads the shipped `registry.json` shape and returns **empty**.
   While it does, a work-order coverage claim on a public corpus is **REFUSED**, in ADR 0040's
   tripwire idiom. Do not infer a maintenance window from a process clock, a recipe step, or a
   quiet stretch.

8. **Nothing is logged.** No row is appended to `eval_runs/log.jsonl`. 646.58, 53.26 and CERT
   6B's 0.104 are untouched, and `templates.py` matchers and priors were not edited.

## Consequences

**Gained.** The inlet is reachable from a real system for the first time. A partner conversation
(P1) can now ask for a named export in a named format rather than for "your maintenance data", and
the answer plugs into machinery that already exists and is already tested.

**Gained, second.** The refusals are the interesting part. Four failure modes that would have been
invisible — a forgotten file reading as an alibi, a renamed column shifting every window, a typo'd
asset id quietly exonerating nothing, a cancelled order counting as authorisation — are now
loud.

**Cost.** Nothing is measured. There is no export on disk, so this ADR reports a built mechanism
and a standing refusal, not a number. The claim that a work order improves any queue or any
explanation split remains **unearned**.

**Not done, deliberately.** The ADR 0068 link — coverage as an operator-queue severity — is *not*
wired. `covering_order` is the primitive a future ranking key would call, and it is tested, but
adding an `uncovered` key today would produce a column that reads "unknown" for all 424 HAI alerts
and would change the frozen queue report to say nothing. That waits for an export.

## Alternatives considered

- **Synthesise work orders for HAI to show the join working end to end.** Rejected, and this is
  the tempting one. HAI labels attack windows, not sanctioned change; inventing a maintenance
  calendar and measuring against it would be scoring our own fiction, and the roadmap's E3
  `success_is_not` names exactly this ("Inventing work orders from process clocks").
- **Return `()` for a missing export instead of raising.** Rejected. It reads as "no maintenance
  happened", which is the most dangerous available lie.
- **Fuzzy-match asset ids so imperfect exports still join.** Rejected. A prefix match lets one
  order exonerate units it never named, and the failure is silent.
- **Treat an unknown status as sanctioning, to be permissive.** Rejected. Permissive here means
  a cancelled order exonerating an attacker.
- **Add an `uncovered` ranking key now.** Rejected — see Consequences. A key whose every value is
  "unknown" is not a measurement.
