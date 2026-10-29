# 50 — Three published detectors, checked against their own table

Three simple detectors from a 2022 paper (Wolsing and colleagues, "Can industrial intrusion detection be SIMPLE?") are now in the harness under their own names: MinMax, Steadytime, and Histogram. The paper tried them on the HAI plant and printed a table. The public code is still online. Gradient is in that table too, and the current public code does not contain it as a detector, so it was left out.

The check used HAI 20.07, which is the release the paper is citing, both of its training files and both of its test files. One training file is not entirely quiet: 776 rows are labelled as attacks, and those rows were not used to learn "normal."

MinMax caught 33 of the 38 attack stretches. The paper says 86%. 33 of 38 is 86.84%, which sits next to that headline and is not the same claim. The rest of the paper's row does not come out. Their MinMax precision is 0.87. This run's is 0.0682. Their F1 is 0.53. This run's is 0.1238. Most of the extra alarms are one sensor, `P1_PCV02Z`, whose ordinary range is only about a quarter of a unit wide. That sensor was not dropped to make the table look closer.

Steadytime and Histogram each caught 7 of 38 stretches, and on this run they raised the same alarms. The paper also prints those two as the same row, at 28% and F1 0.19. This run's F1 is 0.0243.

No comparison with Atlas was made. The draft pass marks in the sixteen-week plan were not used. No frozen number moved.
