# 72 — Six of twelve

PHOS set itself twelve tests for version 1 and froze them before trying. After one more night of
work, six pass.

The new one: every number Atlas reports comes from one set of settings, not one per dataset.

Two tests were taken once and failed. Atlas's alert queue still does not put real attacks near the
top often enough: 57 attacks of 203, where 102 were needed. And the Sentiel signal we did not trust
failed on a larger dataset: it found 1 insider where the old method found 59. Ordinary people in that
dataset never visit a site nobody else uses, so the signal was reading how the data was made.

A seventh looked like a pass and was not counted: the new Sentiel features were scored with an empty
list of things to look for, so they could only ever say zero. Of the rest, one needs a person: an engineer
timing the setup on a new plant. Two need more code first: one command that rebuilds every number
from the data, which someone outside the project then runs.
