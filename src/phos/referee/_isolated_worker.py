"""Entry point for an isolated detector run. Never imported except by `phos.referee.integrity`.

Runs inside a subprocess whose working directory holds a label-free telemetry copy (and, when the
plant has one, a capture) and nothing else — no ``labels.json``, no ``manifest.json``, no seed
file. This module loads a `Dataset` straight from that directory with no ground truth attached,
resolves a detector by a ``module:function`` factory string, runs it, and prints its detections as
JSON on stdout. Anything printed to stderr or a non-zero exit is read by the parent as a failure.

**The plant name the detector sees is not the plant's real id.** A generated plant's id is built
from its family and its master seed (``level-flow-96011``), so handing it to a detector would hand
over the seed through the detector's own input — the detector could regenerate the plant, or look
up which family it came from, without ever opening a label file. The caller passes an opaque token
instead, and `phos.referee.integrity` generates it. This module does not derive it and does not
know what it stands for.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pandas

from phos.eval import Dataset
from phos.ontology import Domain, Observation
from phos.synth.telemetry import TIMESTAMP_COLUMN, entity_id


def _load_unlabelled(telemetry_path: Path, opaque_name: str) -> Dataset:
    """Return a `Dataset` from a label-free telemetry CSV, with no attack or unscored intervals.

    Args:
        telemetry_path: The stripped CSV: a timestamp column and one column per signal.
        opaque_name: The name to record as the dataset's name and entity id. Deliberately not the
            plant's real id, which carries its family and seed. See this module's docstring.

    Returns:
        A corpus with no ground truth at all, because none was given to build one from.
    """
    frame = pandas.read_csv(telemetry_path)
    value_columns = [str(column) for column in frame.columns if column != TIMESTAMP_COLUMN]
    timestamps = [
        stamp.to_pydatetime() for stamp in pandas.to_datetime(frame[TIMESTAMP_COLUMN], utc=True)
    ]
    columns = {column: frame[column].to_numpy(dtype=float) for column in value_columns}
    entity = entity_id(opaque_name)
    observations = [
        Observation(
            id=f"obs_iso{row_index:08d}c{column_index:02d}",
            entity_ids=[entity],
            feature=column,
            value=float(columns[column][row_index]),
            timestamp=timestamp,
            domain=Domain.ATLAS,
            context={},
        )
        for row_index, timestamp in enumerate(timestamps)
        for column_index, column in enumerate(value_columns)
    ]
    return Dataset(name=opaque_name, domain=Domain.ATLAS, observations=observations)


def main(argv: list[str]) -> int:
    """Run the worker: ``argv`` is ``[prog, factory, telemetry_path, opaque_name]``.

    Returns:
        ``0`` on success, after printing the detections as a JSON array to stdout. Any exception
        is left to propagate and reach the parent as a non-zero exit with a traceback on stderr,
        which `phos.referee.integrity.run_detector_isolated` reports as an `IntegrityError`.
    """
    _, factory_path, telemetry_arg, opaque_name = argv
    module_name, _, function_name = factory_path.partition(":")
    factory = getattr(importlib.import_module(module_name), function_name)
    detector = factory()
    dataset = _load_unlabelled(Path(telemetry_arg), opaque_name)
    detections = detector.run(dataset)
    print(json.dumps([detection.model_dump(mode="json") for detection in detections]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
