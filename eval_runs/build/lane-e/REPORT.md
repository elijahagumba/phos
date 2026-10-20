# Lane E — naming, confidence, root cause

19 October 2026. Branch `build/lane-e-atlas`. ADRs 0170–0173. The champion `atlas-v1-consistency` was not edited. `eval_runs/log.jsonl` was not appended. These numbers are synthetic. They are not a claim about a real plant.

## Naming (target 2)

ADR 0170. A control coupling bars only its own actuator outputs, so loop sensors can take a level form.

| Split | Caught | Named right | Named wrong | Right share |
| --- | ---: | ---: | ---: | ---: |
| Development, nine sensors, before | 156 | 96 | 1 | 0.615 |
| Development, nine sensors, kept | 156 | 153 | 0 | 0.981 |
| Held-back 97101–97120, nine sensors | 150 | 146 | 0 | 0.973 |
| Development guard, every sensor, kept | 460 | 398 | 7 | 0.865 |
| Held-back guard | 442 | 384 | 5 | 0.869 |

The nine-sensor bar (at least 70% right, wrong not up) is met on development and on the one held-back look. Chlorine residual, distribution pressure, and reactor pressure are inside that nine. The held-back right share is 0.8 points under development. Wrong names on the nine stayed at zero.

## Confidence (target 3)

ADR 0171. High means the evidence shape's Wilson 95% lower bound is at least 0.8. The number is not surfaced as a user confidence.

| Split | Contentful leads | High | High and right |
| --- | ---: | ---: | ---: |
| Development, out of fold | 36 | 33 | 33 of 33 |
| Held-back, map fitted on development only | 27 | 27 | 27 of 27 |

On development the three wrong leads scored 0.250 and the right leads scored 0.970, with no shared calibrated score. Held-back had no wrong contentful lead, so that separation was not retested.

## Root-cause ranking

ADR 0172. The rank explains an alert. It does not change the alert.

| Split | Window alerts | Liar ranked first | In the first two |
| --- | ---: | ---: | ---: |
| Development | 1,961 | 1,226 (0.625) | 1,415 (0.722) |
| Held-back | 1,919 | 1,175 (0.612) | 1,384 (0.721) |

## Not scored (ADR 0173)

| Capability | Why there is no number |
| --- | --- |
| Slow drift | The scored liar is a step hold, not a ramp |
| Event fusion | Not built. HAI 20.07 was not opened for it |
| Redundancy voting | Naming moved under ADR 0170. No second voter |
| Command baseline | ICSSim did not start (loopback addresses need extra privileges). No 4SICS pcap on disk |
| Maintenance rank | Not added. Lane B's closer still needs a work order |
| GRFICS | Docker and Podman are not installed |

## Scorecard

| Field | Naming | Confidence | Root cause |
| --- | --- | --- | --- |
| catches_within_budget | not this lane | not this lane | not this lane |
| falsified_sensor_passes | 153/156 dev, 146/150 held-back | not this | not this |
| naming_right | 153 dev, 146 held-back | not this | 1,226 dev, 1,175 held-back |
| naming_wrong | 0 dev, 0 held-back (nine sensors) | not this | not this |
| calibration | not this | 33/33 dev, 27/27 held-back | not this |
| runtime | naming dev 21 s; held-back look 134 s for all three | included | root-cause dev 33 s |
