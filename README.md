# STS2 RNG Predictor

Small Python project for predicting correlated Slay the Spire 2 RNG outputs from observed RNG call ranges.

## Usage

From this directory:

```bash
uv run python -m sts2_rng_predictor --self-test
uv run python -m sts2_rng_predictor --example
```

As a library:

```python
from sts2_rng_predictor import CallSpec, Observation, Target, predict_distribution
```

See [docs/rng-correlation-calculator.md](docs/rng-correlation-calculator.md) for the model, examples, and limitations.
