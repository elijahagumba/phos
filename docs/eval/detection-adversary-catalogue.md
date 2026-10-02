# Detection-adversary catalogue (specification)

This is a **specification**, not a detection scoreboard. Hostile configs 04–07 remain
software-survival ([ADR 0017](../adr/0017-the-breaking-harness-fingerprint-classification-and-judging-from-true-state.md),
[ADR 0041](../adr/0041-input-hostile-report-must-not-overwrite-detection.md)). Nothing here
overwrites a breaking detection report.

Code: `phos.eval.adversary.DETECTION_ADVERSARY_SCENARIOS`.

| Id | Engine | What it tries to do |
|---|---|---|
| `gradual-drift` | Atlas | Slow process drift inside a joint ellipsoid learned on the old regime |
| `maintenance-mimicry` | Atlas | Unauthorised writes on a known station that look like engineering maintenance |
| `slow-command` | Atlas | Command-rate change stretched below the live window |
| `sensor-dropout` | Atlas | Missing instruments that look like no-observation rather than a deviation |
| `correlated-manipulation` | Atlas | Coordinated sensor writes that stay on the learned manifold |
| `low-and-slow-identity` | Sentiel | Compromised account that stays inside the user's own history until one sequence |
| `legitimate-role-transition` | Sentiel | Declared role change that self-history treats as departure |
| `cold-start` | Sentiel | New employee with no self baseline; must not invent a peer win |
| `seasonal-load` | Sentiel | Calendar-normal volume that a pooled org baseline calls unusual |
| `shared-account` | Sentiel | One directory identity used by several people |

A later report that scores these scenarios must live **beside** detection logs, not inside them.
