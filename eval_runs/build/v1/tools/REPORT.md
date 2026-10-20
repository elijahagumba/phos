# Tools lane — C2 and A7

| Criterion | Verdict | Number | Record |
| --- | --- | --- | --- |
| C2 | not met | human trial not run | `eval_runs/build/v1/tools/c2-trial.md` |
| A7 | not met | outside person has not run it | `scripts/reproduce_v1.py` |

The pass bars are the ones in `docs/v1-roadmap.md` §2.1 A7 and §2.3 C2. They are not reworded.

C2's tool is `phos.atlas.onboarding` (ADR 0220). Suggestions are not declarations. The morning trial has not been run.

A7's command is ready: `uv run python scripts/reproduce_v1.py` checks the committed records and prints `record intact` (ADR 0221, `docs/reproduce.md`). It does not rescore, and it does not open validation corpora. A7 is met only when someone outside the project has run it. That has not happened.
