# Detection-adversary catalogue (specification)

This is a **specification**, not a detection scoreboard. Hostile configs 04-07 remain
software-survival (ADR 0017 / 0041). Nothing here overwrites a breaking detection report.

| Id | Engine | What it tries to do | Detection claim |
|---|---|---|---|
| `gradual-drift` | atlas | Slow process drift that stays inside a joint ellipsoid learned on the old regime. | false |
| `maintenance-mimicry` | atlas | Unauthorised writes on a known station that look like engineering maintenance. | false |
| `slow-command` | atlas | Command-rate change stretched below the live occupancy window. | false |
| `sensor-dropout` | atlas | Missing instruments that look like NO_OBSERVATION rather than a deviation. | false |
| `correlated-manipulation` | atlas | Coordinated sensor writes that stay on the learned manifold. | false |
| `low-and-slow-identity` | sentiel | Compromised account that stays inside the user's own history until one sequence. | false |
| `legitimate-role-transition` | sentiel | Declared role change: self-history departs, role-history does not. | false |
| `cold-start` | sentiel | New employee with no self baseline; identity layers must not invent a peer win. | false |
| `seasonal-load` | sentiel | Calendar-normal volume that a pooled org baseline calls unusual. | false |
| `shared-account` | sentiel | One directory identity used by several people; self-history is not a person. | false |

A later report that *scores* these scenarios must live **beside** detection logs,
not inside them.
