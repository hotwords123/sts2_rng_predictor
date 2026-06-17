# STS2 RNG Predictor

Small Python project for predicting correlated Slay the Spire 2 RNG outputs from observed RNG call ranges.

## Usage

From this directory:

```bash
uv run sts2-rng-predictor --self-test
uv run python -m sts2_rng_predictor --example
uv run python -m sts2_rng_predictor --same-counter-example
uv run python scripts/reproduce_leafy_hefty.py
uv run python scripts/reproduce_trash_heap.py --sample-check 1000000
```

The source-inspection scripts read local paths from `.env`:

```dotenv
STS2_CODE_ROOT=../sts2
STS2_LOCALIZATION_ROOT=../localization
```

As a library:

```python
from sts2_rng_predictor import (
    CallSpec,
    IntCall,
    IntObservation,
    IntTarget,
    Observation,
    Target,
    predict_distribution,
    predict_same_counter_fast,
    predict_same_counter_distribution,
)
```

See [docs/rng-correlation-calculator.md](docs/rng-correlation-calculator.md) for usage examples and limitations.
See [docs/rng-math-model.md](docs/rng-math-model.md) for the mathematical model behind the predictor.
See [docs/same-counter-fast-model.md](docs/same-counter-fast-model.md) for the non-enumerating same-counter model.
