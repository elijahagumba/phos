# Separate packages with independence rules (ADR 0450)

**Status:** Accepted  
**Date:** 2026-11-16  
**Parts:** S6–S11

## Context

Parts S6–S11 build the referee, breaker, findings loop, real-data hook and release tooling.
These are new packages that sit beside `phos.atlas`, not inside it. The key design question is
how they relate to Atlas: may the referee import Atlas? May the breaker import the referee?
May the simulator import either?

## Decision

Three packages are created, each with a one-way dependency rule:

| Package | May import | Must not import |
|---------|-----------|-----------------|
| `phos.synth` (simulator, S0–S5) | nothing new | `phos.referee`, `phos.breaker`, `phos.atlas` |
| `phos.referee` (exam, S6) | `phos.atlas` (public surface only), `phos.synth` | `phos.breaker`, anything in `phos.breaker` |
| `phos.breaker` (attack search, S7) | `phos.referee.query` (QueryInterface only), `phos.synth` | `phos.atlas`, `phos.referee` internals (detectors, scoring, runner, corpus, integrity) |

`phos.referee.findings` (S8) and `phos.referee.real_data` (S9) are submodules of the referee
and follow the referee's rules. `phos.release` (S10) imports nothing from `phos.atlas` or
`phos.breaker` internals.

## Rationale

- **The referee may import Atlas** through its public surface only (`AtlasEngine.run`,
  `FittedModel`, `FittedCalibrator`, `SubsystemMap`), because the referee needs to run Atlas to
  score it. It must not import Atlas internals, and Atlas must never import the referee back —
  enforced by `tests/referee/test_independence.py`.
- **The breaker may not import Atlas at all.** It reaches Atlas only through the referee's
  `QueryInterface`, which returns exactly what a user of Atlas would see — never rules,
  weights, thresholds, source code or labels. Enforced by `tests/breaker/test_independence.py`.
- **The simulator may not import the referee or the breaker**, so the generator cannot know
  which of its plants are the exam. Sealed families are the mechanism: they are loadable only
  when `PHOS_SYNTH_ALLOW_SEALED=1`, and the referee (not the generator) decides which pools
  may draw from them.

## Consequences

- `tests/referee/test_independence.py` fails if any module under `phos.synth`, `phos.atlas`,
  `phos.eval`, `phos.models` imports `phos.referee`.
- `tests/breaker/test_independence.py` fails if any module under `phos.breaker` imports
  `phos.atlas` or any referee module that exposes Atlas internals (`detectors`, `scoring`,
  `runner`, `corpus`, `integrity`).
- The referee's `QueryInterface` (`phos.referee.query`) is the only supported path from the
  breaker to Atlas.
- Nothing in this ADR changes `phos.atlas`, any frozen row, any detector, or any default.

## Related

- ADR 0347/0348: S7comm envelope lane (transport only, no application bytes).
- ADR 0422: Build brief G unparked against the refusal register.
- `docs/rules/data-tiers.md`: which corpora may be read.
