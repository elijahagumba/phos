# 53 — The long tests are the real files

The test run had grown from a few minutes to about half an hour. Timed on this machine, the whole suite was 28 minutes 52 seconds. Two scores of the batch-distillation files were 541 seconds and 531 seconds. The rest of the long tail is the same kind of work: load a corpus that has been downloaded, and score it.

Those tests already sit out when the files are not there. Once the files are there, they run. That is the whole change in the clock.

They are now marked slow. The ordinary command leaves them out, and on this machine that run came back to 2 minutes 0 seconds (3675 passed, 82 left out). The full run, which puts them back, is `uv run pytest -m "slow or not slow"`.

What moved is the real-corpus modules (`test_real_dataset`, Atlas `test_real_corpora`, the HAI map, the real calibration tests, and the real CERT tests) plus Sentiel's run on the real CERT release (20 seconds) and the four Atlas checks that share one run on real HAI (about 6 seconds, paid by whichever of them goes first). The small simulated-plant demo stays in the ordinary run. So does anything that stayed under five seconds once those readers were out.

Nothing about a detector changed. No frozen number moved.
