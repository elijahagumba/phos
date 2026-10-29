# Five editions of the same plant, one of them on the shelf

**What this is:** the list of every HAI file the publisher actually ships, written into the
registry the way the licence was read.

**Why it exists:** the measurements already on the shelf used two files of one edition. The
publisher has four editions, plus a companion called HAIEnd. A comparison that only knows the
two files cannot say it was scored where other people score.

## What was read

The catalogue is the GitHub tree at one commit, `2a814ceb`, read on 4 October 2026. There is
no separate HAI 1.0 sitting beside it. The README says 20.07 is the bug-fixed release of that
first edition.

The licence heading says Creative Commons Attribution-ShareAlike 4.0. There is no `LICENSE`
file. Lower down, a metadata table on the same page says Attribution 4.0 and leaves out
ShareAlike. Two sentences on one page that disagree are not two confirmations. The heading is
what the existing HAI entry already followed, and the disagreement is written next to it.

## What was not downloaded

The new names are not fetchable.

The oldest edition, 20.07, is four real files. Open one and the columns are separated by
semicolons, not commas. The tool that prepared the edition already on the shelf would see a
single column. The publisher's own table also repeats the names of the first train and test
files for the second pair. The files are `train2` and `test2`.

The edition already in use, 21.03, has eight files, not two. The other six have the same
shape as the two we prepared: 84 columns, labels at the end. They are listed, and they are
not folded into the prepared corpus, because that would rewrite the manifest the frozen
numbers were computed from.

From 22.04 onward the CSV blobs in git are pointers, about 130 bytes, that name a file in
Git Large File Storage. Downloading the link stores the pointer and calls it the dataset.
22.04's short summary texts are real, and they were read: they call the label `Attack`, and
they count 7, 17, 10 and 24 attacks in the four test files. The tables themselves were not
opened. 23.05 and HAIEnd are pointers all the way through, summaries included, so their label
columns are unknown. HAIEnd's label files have the same fingerprint as HAI 23.05's. The
publisher's web page links those two directories under each other's names; the registry
follows the directory names.

Boiler drawings, a PDF manual and a notebook in the same repository are not editions, and
they are not entries.

Nothing here is a new detection number. 646.58 and 53.26 stay where they were.
