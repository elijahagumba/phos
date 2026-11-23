# ADR 0462 — ADR 0453's reopening argument is void

- **Status:** Accepted
- **Date:** 2026-11-23
- **PART:** Method. Voids one argument. No scoring.
- **Supersedes:** [ADR 0453](0453-lift-adr-0067-conditions-for-reopening-corpora.md)
- **Depends on:** [ADR 0067](0067-follow-up-corpora-and-partner-icd-stay-closed.md),
  [ADR 0461](0461-the-17-november-sweep-is-recorded-and-the-tainted-detectors-refuse.md)

## Context

ADR 0453, status Declared, proposes to lift ADR 0067's closure of SWaT, WADI, ICSSim fault data, CERT r4.2 and partner ICD. Its hypothesis gives the reason as weak detection on two corpora: **3/219 attack rows on BATADAL** and **0/61 attack rows on HAI**.

Those two counts were measured on corpora `docs/rules/data-tiers.md` says never to read, score or iterate on. A reopening argument that rests on them does not hold. The counts are quoted here so the voided premise is checkable. They are not a result, and they are not to be repeated as one.

`README.md` and `PROGRESS.md` do not quote either count. Nothing there needed a correction. ADR 0453's own text is left as it was written, so the premise stays visible, and its status now points here.

## Decisions

1. **The reopening argument is void.** ADR 0067 is not lifted. SWaT and WADI stay never-use by licence. ICSSim fault data, CERT r4.2 and partner ICD stay closed on the terms ADR 0067 already set.

2. **`swat_detector` refuses** before it looks at the path it was given (ADR 0461). A factory that waits for a form is still a consumption path for a barred corpus. It does not run.

3. **No new bar replaces ADR 0453.** A later record may propose conditions for a corpus the licence allows. It may not cite a measurement from `hai`, `hai-21.03`, `hai-22.04`, `hai-23.05` or `batadal` as the reason.

## What this record does not do

- It does not edit the hypothesis of ADR 0453, and it does not rewrite the commit that added it.
- It does not score SWaT, HAI or BATADAL.
- It does not move a frozen number. v1 stays 8 of 12.

## What would reverse this

A record that supersedes this one, whose reason is not a measurement on a never-read corpus, and whose corpus the licence allows.
