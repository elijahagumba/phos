#!/usr/bin/env python3
"""Read-only probe: what a CERT release's labels promise, and whether this reader can read its logs.

Answers the two questions that decide whether integrating another CERT release is worth a
multi-gigabyte download, and answers both **without downloading anything**. It reads only files
already on disk, writes nothing, and never touches the network.

**Probe 1 — the scenarios.** `answers/insiders.csv` names every labelled incident in every release,
and `answers/scenarios.txt` describes what each red-team scenario did. Both ship in the small
``answers`` archive, so a release's labels are readable long before its events are. The probe counts
insiders per scenario and pairs each with CERT's own description, then attaches the **detection
register** that description is written in — see `SCENARIO_REGISTERS`. That register is what decides
whether a scenario can exercise a given explanation at all, so reading it off CERT's own words
before committing to the download is the cheapest useful thing anyone can do here.

**Probe 2 — the headers.** `phos.sentiel.cert`'s `LogSpec` set was written against real Release 3.1
headers, read off the files rather than off the published schema, and `CertReader` refuses a header
it does not recognise — a missing required column, or a column it cannot account for. ADR 0020 D5
records why: CERT's published schemas do not match its shipped files. So the specs cannot be assumed
to hold for another release. This probe applies exactly the reader's two rules to a release's actual
headers and reports them **non-fatally**, one line per log, which turns "we would have to re-derive
the schema" from a guess into a list. When the release's events are not on disk it says which logs
went unchecked rather than implying they passed.

Nothing here computes a detection number, and nothing here is a benchmark. It is an instrument for
sizing work.

Usage::

    python scripts/probe_cert_release.py                    # r4.2, the release under consideration
    python scripts/probe_cert_release.py --release r3.1     # the release already integrated
    python scripts/probe_cert_release.py --release r5.2
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import re
import sys
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from phos.sentiel.cert import ALL_SPECS, LogSpec  # noqa: E402
from phos.sentiel.labels import INSIDERS_FILENAME, read_insiders  # noqa: E402

__all__ = [
    "SCENARIOS_FILENAME",
    "SCENARIO_REGISTERS",
    "DetectionRegister",
    "LogCompatibility",
    "ProbeError",
    "ReleaseProbe",
    "ScenarioProfile",
    "ScenarioReading",
    "header_compatibility",
    "main",
    "probe_release",
    "read_scenario_descriptions",
    "render",
]

logger = logging.getLogger(__name__)

DEFAULT_CORPUS: Final = REPO_ROOT / "data" / "cert-insider-threat"
SCENARIOS_FILENAME: Final = "scenarios.txt"
DEFAULT_RELEASE: Final = "r4.2"


class ProbeError(RuntimeError):
    """Raised when the probe cannot read what it was asked to read."""


# ------------------------------------------------------------------------------------------------
# What a scenario's own wording says about how it could be detected
# ------------------------------------------------------------------------------------------------


class DetectionRegister(str, Enum):
    """The kind of comparison a scenario's description says would reveal it.

    The register is a property of the *scenario*, not of PHOS: it is what CERT's own text claims the
    tell was. It matters because Sentiel's explanations are separated by register — a corpus whose
    every positive is self-relative cannot distinguish an engine that reasons about peers from one
    that does not, however many insiders it holds.
    """

    SELF_RELATIVE = "self-relative"
    """The tell is a departure from this person's own past."""

    ACCOUNT_NOT_ACTOR = "account-holder-is-not-the-actor"
    """The account acting is not the person it belongs to. `compromised_account`'s register."""

    PEER_RELATIVE = "peer-relative"
    """The tell is a departure from the declared peer group, the person's own past unremarkable."""


class ScenarioReading(BaseModel):
    """A register assigned to a scenario, and the words it was read from.

    The quote is not decoration. This is a *reading* of CERT's prose rather than a measurement of
    CERT's data, so it is exactly the kind of judgement that must be checkable by whoever relies on
    it — the quote is what lets a reader disagree.

    Attributes:
        detection_register: The register this scenario's tell is written in. Spelled out rather
            than called ``register``, which `pydantic.BaseModel` inherits from `abc.ABCMeta`.
        quote: The words in CERT's description the register was read from, verbatim.
        note: What the reading deliberately does not claim, where that is easy to get wrong.
    """

    model_config = ConfigDict(frozen=True)

    detection_register: DetectionRegister
    quote: str
    note: str = ""


SCENARIO_REGISTERS: Final[Mapping[str, ScenarioReading]] = {
    "1": ScenarioReading(
        detection_register=DetectionRegister.SELF_RELATIVE,
        quote="User who did not previously use removable drives or work after hours begins",
        note=(
            "PART 6B read this same sentence and reached the same reading; it is repeated here so "
            "the probe stands on its own."
        ),
    ),
    "2": ScenarioReading(
        detection_register=DetectionRegister.SELF_RELATIVE,
        quote="at markedly higher rates than their previous activity",
    ),
    "3": ScenarioReading(
        detection_register=DetectionRegister.ACCOUNT_NOT_ACTOR,
        quote="uses the collected keylogs to log in as his supervisor",
        note=(
            "The labelled user is the SYSADMIN — the actor — not the supervisor whose account was "
            "used, so the labelled entity's own departure is still self-relative. What is new is "
            "that the corpus contains an account being driven by somebody else at all, which is "
            "the situation compromised_account claims to explain and no earlier release holds."
        ),
    ),
    "4": ScenarioReading(
        detection_register=DetectionRegister.ACCOUNT_NOT_ACTOR,
        quote="A user logs into another user's machine and searches for interesting files",
    ),
    "5": ScenarioReading(
        detection_register=DetectionRegister.SELF_RELATIVE,
        quote="A member of a group decimated by layoffs uploads documents to Dropbox",
        note=(
            "The group appears in the MOTIVE, not in the tell. What is observable is this person "
            "uploading documents they did not previously upload, which is self-relative. Reading "
            "this as a peer-relative positive would manufacture the very unlock the probe exists "
            "to check for."
        ),
    ),
}
"""How each of CERT's five scenarios describes its own tell, with the words it was read from.

Keyed by the scenario number `insiders.csv` uses. A release containing a scenario absent from this
mapping is reported as unread rather than guessed at.
"""


# ------------------------------------------------------------------------------------------------
# What the probe found
# ------------------------------------------------------------------------------------------------


class ScenarioProfile(BaseModel):
    """One red-team scenario as it appears in a given release.

    Attributes:
        scenario: The scenario number, as `insiders.csv` writes it.
        insiders: How many labelled incidents of it this release holds.
        description: CERT's own description, from ``answers/scenarios.txt``, or ``""`` if the file
            does not describe this scenario.
        reading: The register read off that description, or ``None`` when no reading exists.
    """

    model_config = ConfigDict(frozen=True)

    scenario: str
    insiders: int
    description: str = ""
    reading: ScenarioReading | None = None


class LogCompatibility(BaseModel):
    """Whether one activity log's real header is one `phos.sentiel.cert` can read.

    Applies the reader's own two rules — see `phos.sentiel.cert` — without raising, so a whole
    release can be reported in one pass instead of one failure at a time.

    Attributes:
        filename: The log this describes.
        present: Whether the file was found at all.
        missing: Required columns the header does not have. The reader refuses these outright.
        unaccounted: Columns the header has that the spec neither requires nor ignores. The reader
            refuses these too, rather than dropping a column silently.
    """

    model_config = ConfigDict(frozen=True)

    filename: str
    present: bool
    missing: tuple[str, ...] = ()
    unaccounted: tuple[str, ...] = ()

    @property
    def readable(self) -> bool:
        """Whether `phos.sentiel.cert.CertReader` would accept this header as it stands."""
        return self.present and not self.missing and not self.unaccounted


class ReleaseProbe(BaseModel):
    """Everything the probe established about one release.

    Attributes:
        release: The release probed, e.g. ``"r4.2"``.
        insiders: Labelled incidents in it.
        scenarios: One profile per scenario present, in scenario order.
        logs: One compatibility line per activity log, or empty when the events are not on disk.
        events_on_disk: Whether the release's activity logs were found.
    """

    model_config = ConfigDict(frozen=True)

    release: str
    insiders: int
    scenarios: tuple[ScenarioProfile, ...]
    logs: tuple[LogCompatibility, ...]
    events_on_disk: bool

    def registers(self) -> frozenset[DetectionRegister]:
        """Return the distinct registers this release's scenarios are written in."""
        return frozenset(
            profile.reading.detection_register
            for profile in self.scenarios
            if profile.reading is not None
        )

    def insiders_in(self, register: DetectionRegister) -> int:
        """Return how many labelled incidents are written in ``register``."""
        return sum(
            profile.insiders
            for profile in self.scenarios
            if profile.reading is not None and profile.reading.detection_register is register
        )


# ------------------------------------------------------------------------------------------------
# Probe 1 — the scenarios
# ------------------------------------------------------------------------------------------------

_DESCRIPTION_START = re.compile(r"^(\d+)\.\s*(.*)$")


def read_scenario_descriptions(path: Path) -> dict[str, str]:
    """Read CERT's ``scenarios.txt`` into ``{scenario number: description}``.

    The file is prose: a numbered paragraph per scenario, hard-wrapped at column 70. Wrapped lines
    are rejoined so a description can be quoted and searched as one sentence.

    Args:
        path: Either the ``scenarios.txt`` file or the ``answers`` directory holding it.

    Returns:
        One entry per numbered paragraph, whitespace collapsed. Empty if the file is absent, which
        is not an error: the descriptions are commentary, and the counts stand without them.
    """
    source = path / SCENARIOS_FILENAME if path.is_dir() else path
    if not source.is_file():
        logger.warning(
            "%s not found; scenario counts will be reported without descriptions", source
        )
        return {}

    descriptions: dict[str, list[str]] = {}
    current: str | None = None
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        started = _DESCRIPTION_START.match(line.strip())
        if started is not None:
            current = started.group(1)
            descriptions[current] = [started.group(2)]
        elif current is not None and line.strip():
            descriptions[current].append(line.strip())
        elif not line.strip():
            current = None
    return {number: " ".join(parts).strip() for number, parts in descriptions.items()}


def scenario_profiles(answers: Path, release: str) -> tuple[ScenarioProfile, ...]:
    """Return one profile per scenario ``release`` holds, in scenario order.

    Args:
        answers: The ``answers`` directory, or the ``insiders.csv`` within it.
        release: The release to profile, e.g. ``"r4.2"``. The leading ``r`` is optional.

    Returns:
        Profiles ordered by scenario number, each carrying its insider count, CERT's description,
        and the register that description is written in.

    Raises:
        ProbeError: If the labels cannot be read, or name no incident for this release.
    """
    directory = answers.parent if answers.is_file() else answers
    try:
        labels = read_insiders(answers, release)
    except (ValueError, OSError) as error:
        raise ProbeError(f"cannot read the labels for {release}: {error}") from error

    descriptions = read_scenario_descriptions(directory)
    counts: dict[str, int] = {}
    for label in labels:
        counts[label.scenario or "(unnumbered)"] = (
            counts.get(label.scenario or "(unnumbered)", 0) + 1
        )

    return tuple(
        ScenarioProfile(
            scenario=scenario,
            insiders=counts[scenario],
            description=descriptions.get(scenario, ""),
            reading=SCENARIO_REGISTERS.get(scenario),
        )
        for scenario in sorted(counts, key=_scenario_order)
    )


def _scenario_order(scenario: str) -> tuple[int, str]:
    """Sort numbered scenarios numerically, and anything unnumbered after them."""
    return (int(scenario), scenario) if scenario.isdigit() else (1 << 30, scenario)


# ------------------------------------------------------------------------------------------------
# Probe 2 — the headers
# ------------------------------------------------------------------------------------------------


def header_compatibility(
    root: Path, specs: Sequence[LogSpec] = ALL_SPECS
) -> tuple[LogCompatibility, ...]:
    """Apply `phos.sentiel.cert`'s two header rules to a release's real files, without raising.

    The reader refuses a header missing a required column, and refuses one carrying a column the
    spec neither requires nor ignores. This reports both for every log instead of failing on the
    first, because the useful output is the whole list.

    Args:
        root: The release directory holding the activity CSVs.
        specs: The specs to check. Defaults to every log `CertReader` reads.

    Returns:
        One line per spec, in the order given.
    """
    return tuple(_compatibility(root / spec.filename, spec) for spec in specs)


def _compatibility(path: Path, spec: LogSpec) -> LogCompatibility:
    """Read one log's header and compare it with its spec.

    Parses the first *line* rather than the first CSV *record*, so the read is bounded by a line
    however large the file is — r3.1's ``http.csv`` is 12 GB, and a probe should not be able to
    walk it. A header carries no quoted commas, so a line and a record are the same thing here.
    """
    if not path.is_file():
        return LogCompatibility(filename=spec.filename, present=False)
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        first_line = handle.readline()
    raw = next(csv.reader(io.StringIO(first_line)), None)
    header = {name.strip() for name in raw or []}
    return LogCompatibility(
        filename=spec.filename,
        present=True,
        missing=tuple(sorted(spec.required - header)),
        unaccounted=tuple(sorted(header - spec.known_columns())),
    )


def _release_root(corpus: Path, release: str) -> Path | None:
    """Return the directory holding ``release``'s activity logs, or ``None`` if it is absent."""
    for candidate in (corpus / release, corpus / release.lstrip("r")):
        if candidate.is_dir():
            return candidate
    return None


# ------------------------------------------------------------------------------------------------
# Running it
# ------------------------------------------------------------------------------------------------


def probe_release(corpus: Path, release: str) -> ReleaseProbe:
    """Probe one release's labels, and its headers when its events are on disk.

    Args:
        corpus: The ``cert-insider-threat`` directory, holding ``answers`` and any unpacked
            releases.
        release: The release to probe, e.g. ``"r4.2"``.

    Returns:
        What was established. ``logs`` is empty and ``events_on_disk`` false when only the labels
        are present, which is the normal case for a release nobody has downloaded.

    Raises:
        ProbeError: If ``answers/insiders.csv`` is not there, or names no incident for the release.
    """
    answers = corpus / "answers"
    if not (answers / INSIDERS_FILENAME).is_file():
        raise ProbeError(
            f"{answers / INSIDERS_FILENAME} not found. The labels ship in the small answers "
            "archive:\n    python scripts/fetch_datasets.py cert-insider-threat --yes"
        )

    scenarios = scenario_profiles(answers, release)
    root = _release_root(corpus, release)
    logs = header_compatibility(root) if root is not None else ()
    return ReleaseProbe(
        release=release,
        insiders=sum(profile.insiders for profile in scenarios),
        scenarios=scenarios,
        logs=logs,
        events_on_disk=root is not None,
    )


def render(probe: ReleaseProbe) -> str:
    """Return the probe as the report a reader deciding on a download actually needs."""
    lines = [
        f"CERT {probe.release}: {probe.insiders} labelled incident(s) across "
        f"{len(probe.scenarios)} scenario(s)",
        "",
        "SCENARIOS (from answers/insiders.csv and answers/scenarios.txt)",
    ]
    for profile in probe.scenarios:
        reading = profile.reading
        register = reading.detection_register.value if reading is not None else "UNREAD"
        lines.append(f"  scenario {profile.scenario}: {profile.insiders} insider(s) — {register}")
        if profile.description:
            lines.append(f"      {profile.description}")
        if reading is not None:
            lines.append(f"      read from: {reading.quote!r}")
            if reading.note:
                lines.append(f"      note: {reading.note}")

    lines += ["", "REGISTERS PRESENT"]
    for register in DetectionRegister:
        count = probe.insiders_in(register)
        state = f"{count} insider(s)" if count else "ABSENT — no labelled positive"
        lines.append(f"  {register.value}: {state}")
    if DetectionRegister.PEER_RELATIVE not in probe.registers():
        lines.append(
            "  => This release CANNOT test a peer-relative claim. Not one of its scenarios is "
            "written in that register, so PEER_REGISTER_UNTESTED_CAVEAT stands whatever the "
            "insider count is."
        )

    lines += ["", "HEADERS (phos.sentiel.cert LogSpec vs the real files)"]
    if not probe.events_on_disk:
        lines.append(
            f"  The activity logs for {probe.release} are NOT on disk, so NOTHING below was "
            "checked. These are the specs that would have to hold, each written against a real "
            "Release 3.1 header:"
        )
        for spec in ALL_SPECS:
            lines.append(f"    {spec.filename}: requires {', '.join(sorted(spec.required))}")
        lines.append(
            "  Unchecked is not the same as compatible — ADR 0020 D5 records that CERT's "
            "published schemas do not match its shipped files, which is why this probe reads "
            "headers rather than documentation."
        )
    else:
        for log in probe.logs:
            if not log.present:
                lines.append(f"  {log.filename}: NOT FOUND")
            elif log.readable:
                lines.append(f"  {log.filename}: readable as-is")
            else:
                problems = []
                if log.missing:
                    problems.append(f"missing required {', '.join(log.missing)}")
                if log.unaccounted:
                    problems.append(f"unaccounted-for {', '.join(log.unaccounted)}")
                lines.append(f"  {log.filename}: NEEDS WORK — {'; '.join(problems)}")

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Probe a release and print what it found. Reads only; writes nothing."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--release", default=DEFAULT_RELEASE, help="release to probe, e.g. r4.2")
    parser.add_argument(
        "--corpus", type=Path, default=DEFAULT_CORPUS, help="the cert-insider-threat directory"
    )
    parser.add_argument("--verbose", action="store_true", help="log at DEBUG")
    args = parser.parse_args(argv)

    # WARNING rather than INFO by default: the report *is* the output here, and `read_insiders`
    # logs every labelled user it finds — 70 of them for r4.2, which buries the findings.
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        probe = probe_release(args.corpus, args.release)
    except ProbeError as error:
        print(f"probe refused: {error}", file=sys.stderr)
        return 1
    print(render(probe))
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
