ADR 0145: Bet 001 was not run. linear-excess, gaussian-tail and family-max stay as ADR 0093 declared them. CERT r3.1 events and the entity-day trace cache are absent, ndownloader.figshare.com is not an allowed fetch host, and the frozen-scorer JSON cannot rank a new formula, so nothing was downloaded and nothing was retuned.
ADR 0146: Identity features are six counts of declared hosts, destinations and machines, including which of those are new for that user, on a separate stream whose register ships empty. The existing 34 stay unweighted and their values do not change. The stream was not scored.
ADR 0147: CERT r4.2 is declared held out and is not scored. Its events are not on disk. The deposit's recorded hosts are kilthub.cmu.edu and ndownloader.figshare.com, neither of which is an allowed fetch host, so the archive was not fetched and no sha256 was invented.
2026-10-18 | round-2 setup | Lane A rebuilt from origin/build/lane-a-sentiel (2cf6c64) and merged main d137562. pytest on main: 4141 passed, 3 skipped. CERT r3.1 and its trace cache are now on disk and resolve from this folder through linked files.
2026-10-18 | bet-001 | ADR 0148 fixes the ranking before the one run: (-score, user_id, timestamp), cut at 48; a user is found only by one of their own labelled days. First committed as 23b16cc on a local branch before the run, then re-applied here under 0148 because 0145 was taken by round 1.
2026-10-18 | bet-001 | Ran once. Gate reproduced 6B exactly. Lost: CCH0959 best rank 957 (6B), 1497 (linear-excess), 2689 (gaussian-tail), 1356 (family-max); CSF0929 days in 48: 5, 6, 2, 0. Published on the bet page and in bet-001.md. CERT r3.1 is development from here.
2026-10-19 | target-1 | lane-a-dev:depth found=('CSF0929',) precision=0.125 cch_rank=1094 revert
2026-10-19 | target-1 | lane-a-dev:peer-links found=() precision=0.000 cch_rank=1203 revert
2026-10-19 | target-1 | lane-a-dev:chains found=() precision=0.000 cch_rank=2049 revert
2026-10-19 | target-1 | lane-a-dev:role-hours found=() precision=0.000 cch_rank=8296 revert
2026-10-19 | target-1 | lane-a-dev:peer-links+depth found=() precision=0.000 cch_rank=1060 revert
2026-10-19 | target-1 | lane-a-dev:peer-links+chains found=() precision=0.000 cch_rank=119 revert
2026-10-19 | target-1 | lane-a-dev:peer-links+role-hours found=() precision=0.000 cch_rank=7615 revert
2026-10-19 | target-1 | lane-a-dev:all-four found=() precision=0.000 cch_rank=7977 revert
2026-10-19 | target-1 | lane-a-dev:chains+depth found=() precision=0.000 cch_rank=250 revert
2026-10-19 | target-1 | lane-a-dev:peer-links+chains+depth found=() precision=0.000 cch_rank=136 revert
2026-10-19 | s3 | ADR 0194 restates r4.2 held out. Kept scorer is still 6B. peer-links+chains moved CCH0959 to rank 119 and lost CSF0929, so it is not kept.
