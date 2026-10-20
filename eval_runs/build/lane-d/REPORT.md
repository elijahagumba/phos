# Lane D — commands, naming, and calibration

This lane built three measurements on the synthetic plants, registered the TU Wien pilot factory, and stopped where the machine could not go further. Synthetic numbers are a diagnosis. They are not a result on a real plant.

A3 was not scored. Its frozen corpora are HAI and BATADAL. Those are validation corpora, gate look 1 is spent, and they were not opened.

## Commands against physics (A4)

A declared write from the plant's own operator is silence on the command path. It is not treated as an unknown master. When the actuator then fails to travel, that fact supports a sensor or device fault and contradicts engineering maintenance. The cross-signal path does not, by itself, contradict maintenance. The joint bundle therefore separates a pair that neither path separates alone.

The scored loops are water's clearwell-level setpoint against the intake pump, and power's feeder-voltage setpoint against the tap changer. Batch has no control network and is not scored. The champion is `atlas-v1-consistency`, fit on quiet seed 97001.

Development seeds 97001-97020: 20 of 20 passed. The gained pair on every networked stuck run was engineering maintenance against a sensor or device fault. Follow-run mismatches were 0, so false alerts per shift are 0. The bar was met.

The champion also alerted inside the command window on every stuck run and every follow run. `catches_within_budget` 1.0 is that window count. It does not distinguish an actuator that followed from one that was held, and it is not the separation bar.

Held-back seeds 97101–97120 were scored once, after the declaration in `declaration.json`, by `uv run python scripts/lane_d_score.py --split held-back`. Result name `lane-d-heldback`. Again 20 of 20 passed, follow-run mismatches were 0, and the champion again alerted in the window on both the stuck runs and the follow runs. The same caveat applies to `catches_within_budget` 1.0.

Known-link matchers, priors, and `EVIDENCE_STRENGTH` were not changed. The rank stays `(-confidence, template_id)`. Known-station lead 0 of 16 and unknown-master lead 1 of 4 stay apart.

## Naming the lying sensor (W2)

The plant map does not decide the alerts. `atlas-v1-consistency` does. A separate explainer, `lane-d-plant-map-explainer`, uses ADR 0135's naming rules and the map's default of 5 folds. The frozen map defaults still use ADR 0125. Roles come from each plant's signal table.

The three sensors on the bar are filtered turbidity, transformer oil temperature, and reactor temperature. Each is held at 90% of its span over the middle third of the run. A run counts as named right only when every champion alert on that column inside the window is named as that column, and the reconstructed value is within 10% of the span.

Development: water 20 of 20, power 19 of 20 (seed 97005 caught and not named, and not named as something else), batch 20 of 20. Worst reconstruction on those three is 0.045 of span. `naming_right` is 0.95, `naming_wrong` is 0, `falsified_sensor_passes` is 1. The bar was met.

The survey is not the bar. Chlorine residual and distribution pressure were caught on 20 of 20 and named on none. Reactor pressure was named right on 1 of 20, named wrong on 1, and its worst reconstruction was 0.76 of span. Folds were not cut to 3 to recover the survey.

Held-back: all three frozen sensors were named on 20 of 20. Worst reconstruction is 0.028 of span. `naming_right` is 1.0 and `naming_wrong` is 0. The bar was met. Chlorine residual and distribution pressure were again named on none of 20 caught runs. Reactor pressure was named right on 2 of 20 and named wrong on 4, with a worst reconstruction of 0.76 of span.

## Calibration (W5)

The confidence on a hypothesis is the belief update from the frozen priors. On the command scenarios, a contentful lead is right when a stuck actuator leads with a sensor fault, and wrong when a follow run or a quiet run leads with any contentful explanation. Silence (`insufficient_evidence`) is not in the chart.

Development, 36 contentful leads: 33 right, 3 wrong. The wrong three sit at raw confidence 0.355, the same figure as thirty of the right ones. Three right leads sit at 0.488. Nothing reached 0.8. The gap between the raw confidence and the observed frequency is 0.550. A Platt fit barely moves (coefficient 0.033) and repeats the base rate of this mix, about 0.917. That map is not shown. `calibration` is null. The bar was not met. The chart is `reliability-development.svg`.

Held-back, with no new Platt fit: 27 contentful leads, all right, at the same two raw confidences, and 13 stuck runs stayed silent. The gap is 0.640. Nothing reached 0.8. `calibration` is null. The probability is not surfaced. The bar was not met. The chart is `reliability-heldback.svg`.

## TU Wien

Record vs6hv-1vs74, version 1.0.0, DOI 10.48436/vs6hv-1vs74, CC BY 4.0. The metadata lists nine files and 146,683,465,352 bytes. Development is `tf_a.zip` only (43,271,721,723 bytes, MD5 `e1e689c877b45858fc6c41fd000f85da`). Held-back is `tf_s.zip` only and was not downloaded. Attack-day zips, the unlabelled Tuesday file, `images.zip`, and `extractions.zip` are in neither half. ADR 0163 records the split. The August refusal stands: this is not a command-attack corpus, and catches are not counted.

The development download was started only after ADR 0163 was committed. `tf_s.zip` was not requested. When the lane process stopped, `tf_a.zip` was 29,002,399,744 bytes of 43,271,721,723 and curl was still running. The zip was not opened, and the md5 was not checked.

## GRFICS

Not generated. Docker is not installed, and podman is not installed. No GRFICS code was copied into the repository. Runs 97201-97210 were not produced. Runs 97301-97310 were not generated and were not opened. Credit Fortiphyd remains due when a run is published; this lane has no run to publish.

## What else did not run

4SICS pcaps are not on this machine. `phos-icssim-dev` contains `roles.toml` and no runs. `phos-icssim-heldout` and `netresec-4sics-heldout` were not opened. Margin over a rival, margin over chance, and maintenance closures belong to other lanes and stay null.

## Scorecard

| Key | Development | Held-back |
| --- | ---: | ---: |
| A4 seeds passed | 20/20 | 20/20 |
| catches_within_budget | 1.0 (window count) | 1.0 (window count) |
| false_alerts_per_shift | 0 | 0 |
| naming_right | 0.95 | 1.0 |
| naming_wrong | 0 | 0 |
| reconstruction_error | 0.045 | 0.028 |
| falsified_sensor_passes | 1 | 1 |
| calibration | null | null |
| A4 bar | met | met |
| Lane naming bar (3 sensors chosen on development) | met | met |
| W2 (`docs/phos-2027.md`, all caught runs) | not met: 96/156 right (62%), 1 wrong | not scored on all sensors |
| W5 bar | not met | not met |
