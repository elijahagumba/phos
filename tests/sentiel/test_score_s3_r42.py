"""The r4.2 one-shot refuses a second run and does not read the corpus to do so."""

import subprocess
import sys
from pathlib import Path


def test_an_existing_result_is_not_scored_again(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    out = tmp_path / "s3-r42.json"
    out.write_text('{"already": true}\n', encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "score_s3_r42.py"),
            "--out",
            str(out),
            "--data-dir",
            str(tmp_path / "missing"),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert out.read_text(encoding="utf-8") == '{"already": true}\n'
    assert "already exists" in completed.stderr + completed.stdout
