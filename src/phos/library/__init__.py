"""The dataset library: synthetic OT packs and IT person-days for adversarial evaluation.

Not a public corpus. See `phos.library.caveats`.
"""

from phos.library.caveats import (
    ATTACKS_ARE_OURS_CAVEAT,
    LIBRARY_NOT_PUBLIC_DATA_CAVEAT,
    MODEL_NOT_REALITY_CAVEAT,
    PERSON_DAYS_ARE_OURS_CAVEAT,
    SYNTHETIC_LIBRARY_CAVEATS,
)
from phos.library.evaluate import (
    ATLAS_DWELL_SAMPLES,
    evaluate_it_library,
    evaluate_ot_library,
    library_root,
    write_run_summary,
)
from phos.library.it import (
    IT_FEATURES,
    ItPersona,
    generate_it_library,
    it_catalogue_payload,
    it_person_days,
    it_personas,
    load_it_library,
)
from phos.library.ot import (
    LIBRARY_DIRNAME,
    SAMPLE_INTERVAL_SECONDS,
    SEEDS,
    SUBTLETIES,
    generate_ot_library,
    ot_catalogue_payload,
    ot_packs,
    ot_scenario_count,
    ot_trains,
    write_ot_catalogue,
)

__all__ = [
    "ATLAS_DWELL_SAMPLES",
    "ATTACKS_ARE_OURS_CAVEAT",
    "IT_FEATURES",
    "LIBRARY_DIRNAME",
    "LIBRARY_NOT_PUBLIC_DATA_CAVEAT",
    "MODEL_NOT_REALITY_CAVEAT",
    "PERSON_DAYS_ARE_OURS_CAVEAT",
    "SAMPLE_INTERVAL_SECONDS",
    "SEEDS",
    "SUBTLETIES",
    "SYNTHETIC_LIBRARY_CAVEATS",
    "ItPersona",
    "evaluate_it_library",
    "evaluate_ot_library",
    "generate_it_library",
    "generate_ot_library",
    "it_catalogue_payload",
    "it_person_days",
    "it_personas",
    "library_root",
    "load_it_library",
    "ot_catalogue_payload",
    "ot_packs",
    "ot_scenario_count",
    "ot_trains",
    "write_ot_catalogue",
    "write_run_summary",
]
