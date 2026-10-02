"""``phos demo``: one simulated incident through Atlas, read the way a person would read it.

A demonstration, not a measurement: the plant is simulated and the adversary is ours. What it shows
is real output from the engine, from the capture to the brief.
"""

from phos.demo.pipeline import PLANT, DemoResult, Scenario, Stage, run_demo
from phos.demo.render import Style, render_header, render_result, render_stage

__all__ = [
    "PLANT",
    "DemoResult",
    "Scenario",
    "Stage",
    "Style",
    "render_header",
    "render_result",
    "render_stage",
    "run_demo",
]
