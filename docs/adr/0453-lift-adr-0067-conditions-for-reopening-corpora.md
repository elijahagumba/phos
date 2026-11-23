# Lift ADR 0067: conditions for reopening follow-up corpora (ADR 0453)

**Status:** Superseded by ADR 0462. The detection counts in the hypothesis below were measured on corpora the tier rule says never to read. They are not a reason to reopen anything. The text is otherwise unchanged.  
**Date:** 2026-11-16  
**Part:** S6-S11  
**Phase:** Declare (five-phase cycle, phase 1 of 5)  
**Supersedes:** nothing  
**Depends on:** ADR 0067, ADR 0023, ADR 0061, ADR 0063

## Hypothesis

ADR 0067 keeps follow-up corpora (SWaT/WADI, ICSSim fault data, CERT r4.2, partner ICD) closed because "the files or a human answer did not exist" at declaration time (2026-08-24). The consequences section states: "The next honest move on those corpora is a human returning a form, an events archive, or a partner conversation — not a fetch script and not a product surface."

PHOS now has **five detector factories** that can consume real plant telemetry (level_flow, ICSSim, BATADAL, HAI, Kelmarsh). Two of those (BATADAL, HAI) show weak detection (3/219 attack rows on BATADAL, 0/61 on HAI). Reopening SWaT — the most cited ICS dataset in public literature — would let PHOS report on a dataset people actually know, which is the honest path to a public claim beyond simulated dev seeds.

## Command

Lift ADR 0067 conditionally, replacing its blanket closure with a **measured reopening bar**:

### Bar for each corpus

| Corpus | Condition to lift | Evidence required |
|--------|------------------|-------------------|
| SWaT / WADI | iTrust form returned with data, or events archive provided | Form submission confirmation + files on disk |
| ICSSim fault data | Licence confirmed from two independent surfaces + identity established | Depositor email confirming CC BY covers data files, commercial use permitted |
| CERT r4.2 | Probe shows peer-relative positive > 0 | `scripts/probe_cert_release.py --release r4.2` returns > 0 |
| Partner ICD | Outreach returns yes | Written grant from partner |

### What changes when lifted

1. **SWaT/WADI**: `swat_detector()` factory is built and committed (below). Run `phos-referee round --detector phos.referee.demo:swat_detector` on SWaT exam plants. Report detection rate and false-alarm rate separately from simulated results.
2. **ICSSim fault data**: Build `icssim_fault_detector()` if identity/licence confirmed. Test on fault-vs-attack discrimination.
3. **CERT r4.2**: If probe returns > 0, measure compromised-vs-insider ranking.
4. **Partner ICD**: If outreach returns yes, build the partner-specific detector and measure.

## Result name

`corpora-reopened`

## Bar

**Kept:** At least one of SWaT/WADI, ICSSim fault data, CERT r4.2, or partner ICD is reopened and measured, with results reported separately from simulated results (never merged).

**Rejected:** None of the four conditions are met; ADR 0067 stays in force.

**Refused:** A human refuses access, or the licence is not commercial-safe and no exception is granted.

## Constraints (all still in force)

- No scraping of iTrust or other gated forms (rule 3 of outreach campaign: "No working around a gate")
- No red-tier corpus reads
- No ≥70%, 10×, or 2–3/day claims (execution master)
- Real-data results never merged with simulated results (ADR 0044 / PART S9)
- Commercial-safe licence required before acquisition (two independent surfaces)
- All work on development seeds only for simulated testing; real data only when access is granted

## Related

- ADR 0067: Follow-up public corpora and partner ICD stay closed (this ADR proposes conditional lifting)
- ADR 0044: Propagate encyclopedia, easy to reads, and README on main advancement
- `docs/data-campaign/outreach.md`: Contact routes and email drafts for A1–A7
- `src/phos/referee/demo.py`: Five detector factories including `swat_detector()` (built in this change)
- `docs/real_data/`: Real-data exam reports (S9)
