# HAI correlation-target Mahalanobis — refused at frozen shrinkage

Asked 2026-08-24. `scripts/evaluate_atlas.py hai --protocol three-way --correlation`.

Seed **11**, threshold **3.0**, `dwell_samples=1`. New name only:
`atlas-mahalanobis-correlation` / `ShrinkageTarget.CORRELATION`.

**Result:** `MahalanobisModel.fit` raised before any test score. Training covariance of the
52 non-constant signals is **singular at shrinkage=0.05** (condition number **3.85e+25**).
No row was appended to `eval_runs/log.jsonl`. Public `model:atlas-mahalanobis` **646.58** is
untouched.

Do **not** raise `_shrink` to make this invert. Do not drop signals to manufacture a
detector. ADR 0052 already warned that correlation-target shrinkage can inflate a continuous
holdout; on this HAI three-way train it cannot even be asked.

This is an honest loss of the named option, not a quieter ellipsoid.
