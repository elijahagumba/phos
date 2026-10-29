# 49 — A score for when the alarm is a bit early, and a budget that is not a pass mark

The usual way to score an alarm is to ask whether it landed inside the attack. That is harsh on an alarm that rings a few seconds after the attack has ended, while the plant is still settling, and it is generous to an alarm that covers one sample of a long attack and then goes quiet.

eTaPR (Hwang, Yun, Kim and Min, 2022) scores both of those. Overlap inside the attack counts in full. A short stretch just after the attack counts less and less as it gets further away. A prediction that barely touches an attack can be thrown out. PHOS now computes that score. The check is a hand-built case run through the authors' own package, version 22.6.1: recall 0.425, precision 0.35860968734610654, F1 0.38899242718212823. Same numbers on both sides.

Two details in that package are easy to get wrong, so they are written down. The "how long after the attack still counts" knob is a fraction of the attack's length, not a count of samples, and not the 180 samples the HAI contest used with a different metric. And a stretch after the attack that is only one sample long is ignored.

The other new question is an operator's shift. Alerts are cut into eight-hour blocks. Inside each block only the highest-scoring alerts are kept, as many as you ask for, and then the ordinary window recall is computed on what remains. How many alerts you ask for is an argument. Eight, the number in the v1 roadmap's draft, is not filled in, and nothing has been scored against that draft. No frozen measurement moved.
