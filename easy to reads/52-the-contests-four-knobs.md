# 52 — The contest's four knobs

The HAI contest (HAICon 2020) scored its entries with eTaPR, and the organisers published the four settings they used. Shin, Lee, Yun and Min, in their 2021 write-up of that contest, set them and said they were not allowed to change: alpha 0.5, rho 0.1, pi 0.7, and a tail of 180 samples after each attack.

PHOS already computes eTaPR. The reference package's own default, named `reference-22.6.1`, is a precision threshold of 0.5, a recall threshold of 0.1, and no tail. The contest's precision threshold is 0.7, not 0.5. Its recall threshold is the same 0.1. Those two can be passed to the score.

The other two cannot, not as that function is written. Alpha is a mix of "did you catch the attack at all" and "how much of it did you cover." The package we checked bakes that mix in and does not take alpha as an argument. The 180 is a count of samples on an older scorer that lives in the same package. The newer score's tail is a fraction of the attack's length, between 0 and 1. Passing 180 there is rejected. A run that uses 0.7 and 0.1 with no tail is a legal score, and it is not the contest's score, because the 180 is missing.

The hand-built case from the earlier note does not even tell 0.5 and 0.7 apart. A different small case does, and it matches the authors' package: at 0.5 the F1 is 0.9; at 0.7 it is 0.6.

Nothing has been scored for Atlas against an opponent. These names exist so that, when that comparison happens, it has to say which setting it used.
