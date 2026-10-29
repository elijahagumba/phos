# 130. The bar was written down twice, and not reworded

*A fix moved the code the bar had pinned, so the bar was written again over
the new code. The eight counts were copied, not retyped. ADR 0333, ADR 0335.*

Before you run a check you write down what counts as passing. Otherwise you
run it, look at the answer, and decide afterwards what you were hoping for.

ADR 0333 wrote it down for the law page. Eight counts, each of which has to
come back zero. Does every line on the page name its law. Does any line carry
one of the five words the page refuses. Is any page longer than eight. Does
every law the plant named land in exactly one of held, broken, and unstated.
When there are more breaks than slots, are the ones kept the earliest eight.
And three traps, for things that should never reach a page at all.

That record also pinned the code. Four files, each by a fingerprint of its
contents, so a reader can tell whether the code that was scored is the code
the bar was written for.

Then the fingerprints went stale. A fix on another branch changed one of the
four files, and it was the file the page itself lives in. Merge the fix and
the committed bar describes code that is gone. Leave the fix out and the run
measures a mistake that had already been found and corrected.

The harness does not check those four fingerprints. It refuses a held-out
corpus, and it refuses a plant whose roles have moved, but a reader has to
recompute the fingerprints by hand. So nothing in the run would have caught
it.

ADR 0335 merged the fix and wrote the bar again over the new code. The eight
counts were lifted out of the old record by a script rather than typed again,
and checked afterwards to be the same text to the byte. A bar that drifts
while it is being copied is the exact failure this way of working exists to
prevent, so retyping was removed as a way for it to happen.

Only the fingerprints and the code moved. The bar did not.

Nothing was scored in either record. Version 1 stays at eight of twelve.
