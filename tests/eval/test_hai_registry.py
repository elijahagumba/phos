"""The HAI catalogue in ``data/registry.json`` names every version and file.

Sizes and Git LFS oids were read from commit ``2a814ceb`` of ``icsdataset/hai`` on 2026-10-04.
The integrated ``hai`` entry stays the prepared 21.03 train1/test1 slice. The new entries are
not fetchable: a plain download of the later versions returns a Git LFS pointer, and 20.07 is
semicolon-separated, so the existing comma preparer would misread it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts.fetch_datasets import FETCHABLE_STATUSES, load_registry

REPO = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO / "data" / "registry.json"
PIN = "2a814cebc9a66b06c9e5cd545e2d72e65d383737"
RAW = f"https://raw.githubusercontent.com/icsdataset/hai/{PIN}/"

# repo path, size in bytes, role, content sha256 (Git LFS oid) or None when the blob is the file.
FileRow = tuple[str, int, str, str | None]


def row(path: str, size: int, role: str, digest: str | None = None) -> FileRow:
    return (path, size, role, digest)


HAI_20_07: tuple[FileRow, ...] = (
    row("hai-20.07/train1.csv.gz", 35_252_451, "train"),
    row("hai-20.07/train2.csv.gz", 26_725_939, "train"),
    row("hai-20.07/test1.csv.gz", 32_813_703, "test"),
    row("hai-20.07/test2.csv.gz", 16_907_509, "test"),
)
_T1 = "fdd0162315b32817ba665e2cc8990eb09c47c4edc29683a86b11dc9df062b3a9"
_T2 = "c330af06a24f5fe3df864dddc0e9cbbbfd27db2e005bd32dc8ab3eb2ab356337"
_T3 = "de09120c617bad5f4f3cab86705137fe7ced4b1123fb67ffdf67fd645f3d1b8f"
_E1 = "532de41bed372206941609d05b763958f59abecfd63c8c123649f823452e445e"
_E2 = "c5572e0ed19906107ceb56c4b4f40e165153fc7ba87b3506230d53d2478c29bb"
_E3 = "bff835894baff0c73871bc01ece4f5cf759d455a049e808b012128767420caaf"
_E4 = "51380fd28fd985b94a10cae3d8b80926becb3af9f233f2d3a38ab8be9482a482"
_E5 = "f0d59308b167ed95d0e81fb3e27c906682c9b21d3dba0ab4c4d696565df35179"
HAI_21_03: tuple[FileRow, ...] = (
    row("hai-21.03/train1.csv.gz", 30_651_421, "train", _T1),
    row("hai-21.03/train2.csv.gz", 31_430_645, "train", _T2),
    row("hai-21.03/train3.csv.gz", 67_961_579, "train", _T3),
    row("hai-21.03/test1.csv.gz", 6_149_549, "test", _E1),
    row("hai-21.03/test2.csv.gz", 16_765_328, "test", _E2),
    row("hai-21.03/test3.csv.gz", 15_477_098, "test", _E3),
    row("hai-21.03/test4.csv.gz", 5_602_841, "test", _E4),
    row("hai-21.03/test5.csv.gz", 13_199_829, "test", _E5),
)
# train1 and test1 are the integrated copies. The other six live beside them.
HAI_21_03_DISK: dict[str, Path] = {
    "train1.csv.gz": REPO / "data" / "hai" / "hai-21.03-train1.csv.gz",
    "train2.csv.gz": REPO / "data" / "hai-21.03" / "train2.csv.gz",
    "train3.csv.gz": REPO / "data" / "hai-21.03" / "train3.csv.gz",
    "test1.csv.gz": REPO / "data" / "hai" / "hai-21.03-test1.csv.gz",
    "test2.csv.gz": REPO / "data" / "hai-21.03" / "test2.csv.gz",
    "test3.csv.gz": REPO / "data" / "hai-21.03" / "test3.csv.gz",
    "test4.csv.gz": REPO / "data" / "hai-21.03" / "test4.csv.gz",
    "test5.csv.gz": REPO / "data" / "hai-21.03" / "test5.csv.gz",
}
ON_DISK = frozenset({"hai-21.03", "hai-22.04", "hai-23.05"})
HAI_22_04: tuple[FileRow, ...] = (
    row(
        "hai-22.04/train1.csv",
        53_190_281,
        "train",
        "63383690ffc5344ba68a019c7000854a4d341a22d743ac035f5207072a197b33",
    ),
    row(
        "hai-22.04/train2.csv",
        114_199_064,
        "train",
        "f496991bbef4a6ef5881505aa242fe05cc500b4d5c4cea0d2cf1cf79e4e99285",
    ),
    row(
        "hai-22.04/train3.csv",
        69_953_332,
        "train",
        "4910c49dc07cce238e05c449972a30b7588139ef92d36067f32aadd820e63de7",
    ),
    row(
        "hai-22.04/train4.csv",
        47_917_707,
        "train",
        "81a1c3a8e1726c92c9253602b8628b72d0508a9c260ff21109433ad2b82687bf",
    ),
    row(
        "hai-22.04/train5.csv",
        131_777_589,
        "train",
        "298468467991e73689b61f3cd3975ca21685ef8ba5b5ced4d6a7874f304d9cf7",
    ),
    row(
        "hai-22.04/train6.csv",
        143_438_209,
        "train",
        "717b37b7b88b40885cb6994c9fe00d08a941ec0c3c73801e378f84e846ae35d4",
    ),
    row(
        "hai-22.04/test1.csv",
        50_536_532,
        "test",
        "19627f5dac40c3a5039e7468cfd6c6e4ccd37a85055671e8c349b6bce5f50ed1",
    ),
    row(
        "hai-22.04/test2.csv",
        46_616_720,
        "test",
        "b2ba5d6665deee1c86870a3970417b51a3e640a2cc18b9f8de2d6d8a21979923",
    ),
    row(
        "hai-22.04/test3.csv",
        35_066_591,
        "test",
        "f253f1c78a4a4654d843f8f670a24caa7a72ac91e4418b4505009822b3c55940",
    ),
    row(
        "hai-22.04/test4.csv",
        72_931_406,
        "test",
        "2d2e99ed3364d75d27ab84f0a6523496f7295decf363c90b8a1b9b84e1070376",
    ),
    row(
        "hai-22.04/summary/summary(train1.csv).txt",
        1_373,
        "summary",
        "48d2253a35f7246766af00d49f85c09d7580b600379c59f60918b9d6a1be99b6",
    ),
    row(
        "hai-22.04/summary/summary(train2.csv).txt",
        1_374,
        "summary",
        "6c066e59804e48a76458fe41743d8b4fd8b2ed0ceebc395d2eb15d82282326c2",
    ),
    row(
        "hai-22.04/summary/summary(train3.csv).txt",
        1_373,
        "summary",
        "ab75f967b64231f6b89f423b2b99cdabfa1ce71dcd1e988bcb63736d53cc9350",
    ),
    row(
        "hai-22.04/summary/summary(train4.csv).txt",
        1_373,
        "summary",
        "b03204d67a64d249969bf9bcb9670d2e2fbcfaff41c001b92521f48deb5d1e99",
    ),
    row(
        "hai-22.04/summary/summary(train5.csv).txt",
        1_374,
        "summary",
        "4678ae22da79a24ec0782614ff60c66827782340aa2288c3e8c60d6c595d555c",
    ),
    row(
        "hai-22.04/summary/summary(train6.csv).txt",
        1_374,
        "summary",
        "cd6b37fc81b022d157bc7c41749ee665716ba237999cf6a491e2bfc4e7649200",
    ),
    row(
        "hai-22.04/summary/summary(test1.csv).txt",
        2_156,
        "summary",
        "f7c6e21fd74deb1d731f44344c0356378b49ce36a901e4a7433549f438abc77f",
    ),
    row(
        "hai-22.04/summary/summary(test2.csv).txt",
        2_744,
        "summary",
        "87038e847085ec406f4da6933904ab84eb9b71fc11a266fb26170e5128c72568",
    ),
    row(
        "hai-22.04/summary/summary(test3.csv).txt",
        2_336,
        "summary",
        "a09652b15036f7a31fc146935b5fa4c60c9bea330dffcae02b6e958b82dabad1",
    ),
    row(
        "hai-22.04/summary/summary(test4.csv).txt",
        3_154,
        "summary",
        "0cd5e9e78d02cce1eb980cdf090571601a9b4420ab9d53aa2cfb7c6f9d9581b9",
    ),
)
_LABEL_1 = "eaf69edb9c5834bc393afd7bf658b5e408d34fd7bfc3261f80516765fb818fbc"
_LABEL_2 = "8090c44981176e39b0f01a7126a80248ac0b93355c00f9db4d4e2f2106452b92"
_SUM_1 = "9d8fb32ee1e816c88f93c8d661f90a7736802582d3572a1e1ebd953783353da6"
_SUM_2 = "b564024a105981415a81dd1b338a48ad7ad5be511849884232540f1a6550e5c1"
HAI_23_05: tuple[FileRow, ...] = (
    row(
        "hai-23.05/hai-train1.csv",
        162_418_984,
        "train",
        "53007b0ba604fbf338e7ac2e08cd81d874b5d1388f3aecb213ddcba5bf2bec4a",
    ),
    row(
        "hai-23.05/hai-train2.csv",
        169_121_615,
        "train",
        "0e520e82bf78a661ab19ce4967f3c766bd809820f457a9c90c365102d4534c56",
    ),
    row(
        "hai-23.05/hai-train3.csv",
        72_774_793,
        "train",
        "bfcec2dc05adea103e7491546b0e28268faaa26d3cc717d10f4595c94b81e85d",
    ),
    row(
        "hai-23.05/hai-train4.csv",
        114_494_940,
        "train",
        "56658c83657d42a65db982b864362e0d0ffeb96d1f7b357d5e76e3a5c522d940",
    ),
    row(
        "hai-23.05/hai-test1.csv",
        31_255_559,
        "test",
        "78c7f1d4de1f2ab9ccc2f8c719f80f831033543adb0c81d0d78f84f40838d4be",
    ),
    row(
        "hai-23.05/hai-test2.csv",
        132_946_575,
        "test",
        "b2b8dd295aefd87e39260fe43cb4c73ee86d6264b0ac4b0761e7efb0c2b545c3",
    ),
    row("hai-23.05/label-test1.csv", 1_242_017, "labels", _LABEL_1),
    row("hai-23.05/label-test2.csv", 4_500_018, "labels", _LABEL_2),
    row("hai-23.05/summary_label1.txt", 1_591, "summary", _SUM_1),
    row("hai-23.05/summary_label2.txt", 2_911, "summary", _SUM_2),
)
HAIEND_23_05: tuple[FileRow, ...] = (
    row(
        "haiend-23.05/end-train1.csv",
        256_552_242,
        "train",
        "112ab5a553e53b14f48e6fc7c8b81a844ee82c2bf3284cc422345e129b3af476",
    ),
    row(
        "haiend-23.05/end-train2.csv",
        266_924_893,
        "train",
        "7f2367efabbb2fa5a65ef1e95c06b687c47836577f7b2e7fbee6238e00e41855",
    ),
    row(
        "haiend-23.05/end-train3.csv",
        115_378_733,
        "train",
        "92dbb6a92a4f05cbd5cf9d6d9747a9e9938d544ef7fe1edb1954cabce52a4c08",
    ),
    row(
        "haiend-23.05/end-train4.csv",
        180_186_249,
        "train",
        "b995dabac6321a34e5b69bdd01abec08f7f844dbdc489bdb5f9935a8da0b2038",
    ),
    row(
        "haiend-23.05/end-test1.csv",
        49_351_620,
        "test",
        "e1929829ce3437281eddb97f549121ebc4676384a390136c2b052ce649eb8d58",
    ),
    row(
        "haiend-23.05/end-test2.csv",
        209_737_755,
        "test",
        "587dc7a73eb92dd119dc7e3f902d2fa308b8af47352d1aa388ea5ef9da63390c",
    ),
    row("haiend-23.05/label-test1.csv", 1_242_017, "labels", _LABEL_1),
    row("haiend-23.05/label-test2.csv", 4_500_018, "labels", _LABEL_2),
    row("haiend-23.05/summary_label1.txt", 1_591, "summary", _SUM_1),
    row("haiend-23.05/summary_label2.txt", 2_911, "summary", _SUM_2),
)

CATALOGUE: dict[str, tuple[FileRow, ...]] = {
    "hai-20.07": HAI_20_07,
    "hai-21.03": HAI_21_03,
    "hai-22.04": HAI_22_04,
    "hai-23.05": HAI_23_05,
    "haiend-23.05": HAIEND_23_05,
}


def test_integrated_hai_slice_is_unchanged() -> None:
    """The prepared 21.03 train1/test1 corpus is still the only integrated HAI entry."""
    hai = load_registry().by_name("hai")
    assert hai.status == "integrated"
    assert hai.license.spdx == "CC-BY-SA-4.0"
    assert hai.license.evidence.startswith("'## License'")
    assert [(item.filename, item.size_bytes) for item in hai.files] == [
        ("hai-21.03-train1.csv.gz", 30_651_421),
        ("hai-21.03-test1.csv.gz", 6_149_549),
    ]
    assert hai.prepare is not None
    assert hai.prepare["train"].source_file == "hai-21.03-train1.csv.gz"
    assert hai.prepare["train"].row_stride == 10
    assert hai.prepare["test"].source_file == "hai-21.03-test1.csv.gz"
    assert hai.prepare["test"].drop_columns == ["attack_P1", "attack_P2", "attack_P3"]


def test_every_hai_version_is_registered_and_not_fetchable() -> None:
    """Each version's files match the pinned tree, and ``--all`` will not download them."""
    registry = load_registry()
    for name, expected in CATALOGUE.items():
        entry = registry.by_name(name)
        if name in ON_DISK:
            assert entry.status == "on-disk"
        else:
            assert entry.status == "registered-not-fetched"
        assert entry.status not in FETCHABLE_STATUSES
        assert entry.fetchable is False
        assert entry.prepare is None
        assert entry.release == PIN
        assert entry.domain == "ATLAS"
        assert entry.license.spdx == "CC-BY-SA-4.0"
        assert entry.license.permits_research_use is True
        assert "CC BY-SA 4.0" in entry.license.evidence
        assert "CC BY 4.0" in entry.license.evidence
        assert "schema.org" in entry.license.evidence
        assert PIN in entry.license.evidence
        assert "2026-10-04" in entry.license.evidence
        got = {
            (
                item.url.removeprefix(RAW),
                item.size_bytes,
                item.role,
                item.sha256,
            )
            for item in entry.files
        }
        assert got == set(expected)
        assert all(item.url == RAW + item.url.removeprefix(RAW) for item in entry.files)


def test_licence_contradiction_and_file_traps_are_written_down() -> None:
    """The heading and the metadata table disagree, and the files are not all comma CSVs."""
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    by_name = {item["name"]: item for item in raw["datasets"]}
    assert "hai-1.0" not in by_name
    twenty = by_name["hai-20.07"]
    assert "semicolon" in " ".join(twenty["quirks"]).lower()
    assert "train2" in " ".join(twenty["quirks"])
    full = by_name["hai-21.03"]
    assert "84" in " ".join(full["quirks"])
    assert full["status"] == "on-disk"
    assert "not in git" in " ".join(full["quirks"]).lower()
    later = by_name["hai-22.04"]
    later_text = " ".join(later["quirks"]).lower()
    assert later["status"] == "on-disk"
    assert "pointer" in later_text
    assert "gitattributes" in later_text
    assert "not scored" in later_text
    may = by_name["hai-23.05"]
    may_text = " ".join(may["quirks"]).lower()
    assert may["status"] == "on-disk"
    assert "on disk" in may_text
    assert "not scored" in may_text
    end = by_name["haiend-23.05"]
    end_text = " ".join(end["quirks"]).lower()
    assert "identical" in end_text or "same oid" in end_text
    assert end["files"]  # the label oids are pinned by the catalogue test


def test_hai_21_03_payloads_match_the_registered_sha256() -> None:
    """The checksums are of the files on disk. A missing payload skips; a wrong one fails."""
    missing = [path for path in HAI_21_03_DISK.values() if not path.is_file()]
    if missing:
        pytest.skip("hai-21.03 payloads are gitignored and not on this machine")
    expected = {path.rsplit("/", 1)[-1]: digest for path, _size, _role, digest in HAI_21_03}
    for filename, path in HAI_21_03_DISK.items():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == expected[filename]


def test_later_hai_payloads_match_the_registered_sha256() -> None:
    """22.04 and 23.05 checksums are the files on disk. Missing payloads skip; a mismatch fails."""
    registry = load_registry()
    missing: list[Path] = []
    pairs: list[tuple[Path, str]] = []
    for name in ("hai-22.04", "hai-23.05"):
        for item in registry.by_name(name).files:
            folder = "summary" if "/summary/" in item.url else ""
            path = REPO / "data" / name / folder / item.filename
            if path.is_file():
                pairs.append((path, item.sha256 or ""))
            else:
                missing.append(path)
    if missing:
        pytest.skip("later HAI payloads are gitignored and not on this machine")
    for path, expected in pairs:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
