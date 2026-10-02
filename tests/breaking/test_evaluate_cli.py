"""The breaking-points CLI: --hostile-only must not overwrite the detection maps."""

from pathlib import Path
from types import ModuleType

import pytest
from scripts.evaluate_breaking_points import main

from phos.breaking.outcome import RobustnessOutcome, RobustnessVerdict
from phos.breaking.robustness import CorpusRobustness
from phos.synth.attacks import AttackFlavour, AttackType


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Point the CLI at empty temp directories so a test cannot touch eval_runs/breaking."""
    import scripts.evaluate_breaking_points as module

    attack_dir = tmp_path / "attacks"
    report_dir = tmp_path / "breaking"
    attack_dir.mkdir()
    report_dir.mkdir()
    monkeypatch.setattr(module, "ATTACK_DIR", attack_dir)
    monkeypatch.setattr(module, "REPORT_DIR", report_dir)
    monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    return module


def _touch_corpus(root: Path, name: str) -> Path:
    """Create a corpus directory whose presence discover_attack_corpora will notice."""
    directory = root / name
    directory.mkdir()
    (directory / "manifest.json").write_text("{}", encoding="utf-8")
    return directory


def _hostile_result(name: str) -> CorpusRobustness:
    """A software-survival result. Never a detection outcome."""
    return CorpusRobustness(
        corpus=name,
        outcomes=(
            RobustnessOutcome(
                attack_id="hostile-case",
                attack_type=AttackType.POISONED_BASELINE,
                verdict=RobustnessVerdict.COMPLETED,
            ),
        ),
        loaded=True,
    )


def _stub_hostile_run(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """Measure nothing real: return a fixture robustness row and refuse detection."""

    def run_hostile(directory: Path, corpus: object) -> CorpusRobustness:
        return _hostile_result(directory.name)

    def run_detection(corpus: object, config: object) -> None:
        raise AssertionError("DETECTION corpora must not be measured under --hostile-only")

    def load_attack_corpus(directory: Path) -> object:
        return type(
            "Loaded",
            (),
            {"flavour": AttackFlavour.INPUT_HOSTILE, "name": directory.name},
        )()

    monkeypatch.setattr(module, "run_hostile", run_hostile)
    monkeypatch.setattr(module, "run_detection", run_detection)
    monkeypatch.setattr(module, "load_attack_corpus", load_attack_corpus)


def test_hostile_only_writes_the_robustness_stem_and_never_the_canonical_report(
    cli: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    attack_dir: Path = cli.ATTACK_DIR
    report_dir: Path = cli.REPORT_DIR
    _touch_corpus(attack_dir, "synth-hostile-poisoned-baseline")
    _stub_hostile_run(cli, monkeypatch)

    assert main(["--hostile-only", "--no-log", "--no-commands"]) == 0
    assert (report_dir / "input-hostile-robustness.md").is_file()
    assert (report_dir / "input-hostile-robustness.json").is_file()
    assert not (report_dir / "breaking-report.md").exists()
    assert not (report_dir / "breaking-report.json").exists()


def test_hostile_only_honours_output_stem_without_copying_the_canonical_report(
    cli: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    attack_dir: Path = cli.ATTACK_DIR
    report_dir: Path = cli.REPORT_DIR
    _touch_corpus(attack_dir, "synth-hostile-poisoned-baseline")
    _stub_hostile_run(cli, monkeypatch)

    assert (
        main(
            [
                "--hostile-only",
                "--no-log",
                "--no-commands",
                "--output-stem",
                "my-robustness",
            ]
        )
        == 0
    )
    assert (report_dir / "my-robustness.md").is_file()
    assert (report_dir / "my-robustness.json").is_file()
    assert not (report_dir / "breaking-report.md").exists()
    assert not (report_dir / "breaking-report.json").exists()
    assert not (report_dir / "input-hostile-robustness.md").exists()


def test_hostile_only_skips_detection_flavour_corpora(
    cli: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    attack_dir: Path = cli.ATTACK_DIR
    _touch_corpus(attack_dir, "synth-attack-water-treatment-graded")
    _touch_corpus(attack_dir, "synth-hostile-poisoned-baseline")
    _stub_hostile_run(cli, monkeypatch)

    assert main(["--hostile-only", "--no-log", "--no-commands"]) == 0
    report_dir: Path = cli.REPORT_DIR
    assert (report_dir / "input-hostile-robustness.md").is_file()
    assert not (report_dir / "breaking-report.md").exists()


def test_hostile_only_refuses_a_detection_only_name_list(
    cli: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    report_dir: Path = cli.REPORT_DIR
    code = main(
        [
            "--hostile-only",
            "synth-attack-water-treatment-graded",
            "--no-log",
            "--no-commands",
        ]
    )
    assert code != 0
    err = capsys.readouterr().err
    assert "INPUT_HOSTILE" in err or "input-hostile" in err.lower()
    assert "detection" in err.lower()
    assert not (report_dir / "breaking-report.md").exists()
    assert not (report_dir / "breaking-report.json").exists()
    assert not (report_dir / "input-hostile-robustness.md").exists()


def test_hostile_only_refuses_the_canonical_output_stem(
    cli: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    attack_dir: Path = cli.ATTACK_DIR
    report_dir: Path = cli.REPORT_DIR
    _touch_corpus(attack_dir, "synth-hostile-poisoned-baseline")
    _stub_hostile_run(cli, monkeypatch)

    code = main(
        [
            "--hostile-only",
            "--no-log",
            "--no-commands",
            "--output-stem",
            "breaking-report",
        ]
    )
    assert code != 0
    assert "breaking-report" in capsys.readouterr().err
    assert not (report_dir / "breaking-report.md").exists()
    assert not (report_dir / "breaking-report.json").exists()
