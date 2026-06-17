"""STS2 correlated RNG prediction helpers."""

from .core import (
    CallSpec,
    Observation,
    PredictionResult,
    PredictionTooBroadError,
    Target,
    predict_distribution,
    predict_same_counter_distribution,
    run_example,
    run_same_counter_example,
    run_self_test,
)
from .rng_compat import (
    INT_MAX,
    INT_MIN,
    DotNetCompatRandom,
    derived_seed,
    deterministic_hash_code,
    event_offset_for_id,
    normalize_offset,
    rng_offset_for_name,
    snake_case,
)
from .same_counter import (
    IntCall,
    IntObservation,
    IntTarget,
    SameCounterResult,
    predict_same_counter_fast,
)

__all__ = [
    "INT_MAX",
    "INT_MIN",
    "CallSpec",
    "DotNetCompatRandom",
    "IntCall",
    "IntObservation",
    "IntTarget",
    "Observation",
    "PredictionResult",
    "PredictionTooBroadError",
    "SameCounterResult",
    "Target",
    "derived_seed",
    "deterministic_hash_code",
    "event_offset_for_id",
    "normalize_offset",
    "predict_distribution",
    "predict_same_counter_fast",
    "predict_same_counter_distribution",
    "rng_offset_for_name",
    "run_example",
    "run_same_counter_example",
    "run_self_test",
    "snake_case",
]
