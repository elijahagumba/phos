# 192. The detectors built on sealed data now refuse

*On 17 November a sweep read thousands of files, including corpora this project had promised not to read. The same day, five commits built detectors from those corpora. The detectors now stop before they open a file. The score on the board does not move.*

## What the disk shows

Between 18:59 and 19:03 UTC that day, 14,985 files were read across the copies of this project on the machine. Hidden folders such as `.git` were skipped. Ordinary folders were not. Forty files were in the corpora the rules say never to read: HAI and BATADAL. The two held-back halves of the newer public datasets were read as well. So was most of the older simulated batch that had already been used once.

Nothing in the project says which program did the reading. A backup, a search index, or an assistant with access to the disk would all look the same. This note does not guess.

## What that costs

The older simulated batch stays spent. It was already spent, and the read means it is not treated as unseen. The two held-back halves are not unseen. None of the never-read corpora are unseen.

The number on the board, 87 of 120, is a copy of a result already written down. It was not recomputed from the files the sweep touched. It stays.

## What the code does now

Six ways of building a detector from HAI, BATADAL or SWaT now raise an error before they open a file. SWaT was never allowed, because of its licence, and the note that argued for reopening it used detection counts taken from HAI and BATADAL. That argument is void. The closure stands.

The five scripts that scored those corpora are moved aside, with a header on each saying why. They are kept so the record of what happened is still in the tree. They are not there to be run.

The full account is ADR 0461. The voided argument is ADR 0462.

## Where the files are now

The five never-read corpora and the two held-back halves are no longer in this copy of the project. The owner hashed them first, 62 lines, and that list is in the repository. The files themselves are in an encrypted disk image, mounted only when a referee has declared a score. The detectors still refuse, and the number on the board still does not move.

One other copy on this machine, the `phos-g-dnp3` worktree, still has the folders. Nothing in them was opened to write this note. The full account of the move is ADR 0464.
