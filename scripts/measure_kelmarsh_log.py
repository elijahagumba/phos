"""Score Kelmarsh development SCADA when every year zip matches the registry.

Does not download. Does not open a held-back name. Does not append ``eval_runs/log.jsonl``.
A missing year zip is a block, written under the lane folder, and is not a partial score.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from phos.eval.build_declaration import KELMARSH_DEVELOPMENT_FILES
from phos.eval.kelmarsh_log import (
    KELMARSH_CAVEAT,
    KELMARSH_CITATION,
    combine_zips,
    development_checksums,
    kelmarsh_scorecard,
    load_scada_zip,
    render_kelmarsh_markdown,
    score_halves,
    verify_file,
)

_SCADA: tuple[str, ...] = tuple(
    name for name in KELMARSH_DEVELOPMENT_FILES if name.startswith("Kelmarsh_SCADA_")
)


def main() -> None:
    """Verify the development zips and, if they are all present, write the log score."""
    repo = Path(__file__).resolve().parents[1]
    directory = Path("/tmp/kelmarsh-dev")
    out = repo / "eval_runs" / "build" / "lane-b"
    out.mkdir(parents=True, exist_ok=True)
    registry = json.loads((repo / "data" / "registry.json").read_text(encoding="utf-8"))
    checksums = {item.filename: item for item in development_checksums(registry)}
    missing = [name for name in _SCADA if not (directory / name).is_file()]
    if missing:
        _write_block(out, missing, directory)
        return
    for name in _SCADA:
        verify_file(directory / name, checksums[name])
    started = time.perf_counter()
    loaded = [load_scada_zip(directory / name) for name in _SCADA]
    trains, tests, spans = combine_zips(loaded)
    report = score_halves(trains, tests, spans)
    elapsed = time.perf_counter() - started
    card = kelmarsh_scorecard(report, elapsed)
    payload = {
        "report": report.model_dump(mode="json"),
        "scorecard": card,
        "runtime_seconds": elapsed,
        "files": list(_SCADA),
    }
    (out / "kelmarsh-log.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    body = render_kelmarsh_markdown(report)
    body += f"\nRuntime: {elapsed:.3f} seconds.\n"
    (out / "kelmarsh-log.md").write_text(body, encoding="utf-8")
    share = report.explained_share
    shown = "undefined" if share is None else f"{share:.4f}"
    print(
        f"explained {report.explained_alerts}/{report.alerts} ({shown}); "
        f"false alerts per shift {report.false_alerts_per_shift}; wrote {out}"
    )


def _write_block(out: Path, missing: list[str], directory: Path) -> None:
    present = [name for name in _SCADA if (directory / name).is_file()]
    payload = {
        "measured": False,
        "reason": (
            "Kelmarsh development SCADA zips are not all on disk. The score was not run. "
            "A partial year set is not the development half."
        ),
        "missing": missing,
        "present": present,
        "caveat": KELMARSH_CAVEAT,
        "citation": KELMARSH_CITATION,
    }
    (out / "kelmarsh-log.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Kelmarsh development log",
        "",
        KELMARSH_CAVEAT,
        "",
        "The score did not run. These development year zips were not on disk:",
        "",
    ]
    lines.extend(f"- {name}" for name in missing)
    lines.extend(["", "These year zips were present and were not opened for a partial score:", ""])
    lines.extend(f"- {name}" for name in present)
    lines.append("")
    (out / "kelmarsh-log.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"blocked, missing {len(missing)} of {len(_SCADA)}; wrote {out}")


if __name__ == "__main__":
    main()
