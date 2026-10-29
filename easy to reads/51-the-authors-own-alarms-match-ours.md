# 51 — The authors' own alarms match ours

Note 50 rebuilt three published detectors and could not get the paper's precision. The next check was the authors' own programs, on the same HAI 20.07 files.

Their intrusion-detection program (ipal-iids 1.5.4) was trained and then run on both test files, with every sensor, at the settings in their code: a range twice as wide as the training range, and a cutoff of ten distinct values before a sensor is treated as a switch. The packet transcriber is a different tool and was not part of this. Their HAI converter, as published, expects the later HAI release (commas, eight files). These files are semicolons and there are four of them, so the conversion followed their rules and used the files that exist. Nothing in the recording skips a second, so their "fill the gap" step never ran.

Their MinMax raises 255 alarm-runs that overlap an attack and 811 that do not. The paper says 73 and 7. Precision is 0.06824781904978935, not 0.87. Every alarming row is the same row our MinMax alarms on. Leaving in the 776 training rows that are labelled attacks does not change a single alarm. Their Steadytime and their Histogram raise the same 36,656 alarms as each other, and the same alarms as ours: 9 runs on attacks and 5 off them, not the paper's 15 and 0.

Their evaluator stops unless another package, eTaPR, is installed. The counts above are the evaluator's own alarm and point scores, read from the same library, on the detector's output. None of those outputs carries the "adjust" mark their alarm-extension tool looks for, so extension would change nothing.

Under the frozen rule, the three detectors now count as checked: the authors' code was run, and the alarms agree. The paper's table is still not what that code does. Gradient is still not in their detector tree, so it stays unchecked. Atlas was not put next to any of them. No frozen number moved.
