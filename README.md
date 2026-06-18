# STS2 RNG Predictor

Small Python project for predicting correlated Slay the Spire 2 RNG outputs from observed RNG call ranges.

## Usage

From this directory:

```bash
uv run sts2-rng-predictor --self-test
uv run -m sts2_rng_predictor --example
uv run -m sts2_rng_predictor --same-counter-example
uv run scripts/reproduce_leafy_hefty.py
uv run scripts/reproduce_neows_bones_curse.py
uv run scripts/reproduce_trash_heap.py --sample-check 1000000
uv run scripts/plot_raw_scatter.py 1+transformations 0 --counter 0 --samples 20000 --output results/transform-vs-act.png
```

`plot_raw_scatter.py` hashes non-numeric offset tokens exactly as written. Use
ordinary snake_case for named RNGs such as `transformations` and
SCREAMING_SNAKE_CASE for event ids such as `1+NEOW`.

Saved outputs from the reproduction scripts are indexed in [results/README.md](results/README.md).

The source-inspection scripts read local paths from `.env`:

```dotenv
STS2_CODE_ROOT=/path/to/sts2/code
STS2_LOCALIZATION_ROOT=/path/to/sts2/localization
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

## Credits

This project was inspired by the analysis in [Correlated Randomness in Slay the Spire 2](https://tck.mn/blog/correlated-randomness-sts2/).
The analysis and implementation were completed in collaboration with Codex.
