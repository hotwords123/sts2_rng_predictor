# STS2 RNG 相关性计算器

这份工具用于分析 STS2 中“同一基础 seed + 不同固定偏移”的 RNG 相关性。实现位于 `sts2_rng_predictor/` 包中，既可以作为 Python 库导入，也可以直接运行内置示例和自测。

## 模型

STS2 的 `Rng` 封装使用：

```csharp
_random = new System.Random((int)seed);
```

命名 RNG 的 seed 派生为：

```csharp
new Rng(baseSeed + (uint)GetDeterministicHashCode(name))
```

其中 `RunRngSet` / `PlayerRngSet` 会先把 enum 名称转成 snake case，例如 `CombatEnergyCosts` -> `combat_energy_costs`。工具中的 `rng_offset_for_name()` 会复刻这个规则，所以可以直接传 `"monster_ai"`、`"CombatEnergyCosts"`、`"shuffle"` 这类名称。

`System.Random(int seed)` 会把 32 位 seed 转成 signed int，再对负数取绝对值。工具会精确处理这个折叠、`uint` 加法 wraparound，以及 `int.MinValue` / `int.MaxValue` 的边界特例。

## 基本用法

```bash
uv run python -m sts2_rng_predictor --self-test
uv run python -m sts2_rng_predictor --example
```

作为库导入：

```python
from sts2_rng_predictor import (
    CallSpec,
    Observation,
    Target,
    predict_distribution,
)

full_int = CallSpec(kind="next_int", min_inclusive=0, max_exclusive=2_147_483_647)

observations = [
    Observation(
        offset="monster_ai",
        counter=0,
        call=full_int,
        observed_min=123456789,
        observed_max=123456789,
    ),
    Observation(
        offset="combat_energy_costs",
        counter=2,
        call=full_int,
        observed_min=987654321,
        observed_max=987654321,
    ),
]

target = Target(
    offset="shuffle",
    counter=0,
    call=CallSpec(kind="next_int", min_inclusive=0, max_exclusive=4),
)

result = predict_distribution(observations, target)
print(result.candidate_count)
print(result.distribution)
```

整数观测的 `observed_min` / `observed_max` 是包含端点的结果区间。例如看到一次 `NextInt(4)` 结果为 2，就写 `observed_min=2, observed_max=2`。

## 偏移量

如果知道具体数值偏移，可以直接传整数：

```python
Observation(offset=1703902611, counter=0, call=full_int, observed_min=10, observed_max=20)
```

如果只知道 RNG 类型名称，直接传名称更稳妥：

```python
Observation(offset="MonsterAi", counter=0, call=full_int, observed_min=10, observed_max=20)
Observation(offset="monster_ai", counter=0, call=full_int, observed_min=10, observed_max=20)
```

这两种写法都会使用 `GetDeterministicHashCode("monster_ai")` 得到同一个 32 位偏移。

## 计数器

`counter` 是 STS2 `Rng.Counter` 在这次调用之前的值。一个全新的 RNG 第一次调用是 `counter=0`，调用后 counter 变为 1。`NextInt`、`NextFloat`、`NextItem` 都按一次调用处理；`Shuffle(n)` 需要拆成 `n - 1` 次 `NextInt`。

## 限制

- 至少需要一个 `next_int` 观测。工具用它反推候选 base seed，不做 2^32 全量扫描。
- 观测太宽时会抛出 `PredictionTooBroadError`。这通常表示需要增加观测、使用更窄区间，或显式提高 `max_candidates`。
- v1 不自动推断未知 counter，也不建模完整 `Shuffle`、`NextGaussian*` 或其它会消耗多次底层随机数的组合行为。
- `next_float` 可以作为观测区间过滤；如果目标是 `next_float`，需要在 `CallSpec` 上设置 `buckets`，工具会输出分桶分布。

## 结果解读

`predict_distribution()` 返回 `PredictionResult`：

- `distribution`：目标输出到概率的后验分布。
- `candidate_count`：满足所有观测的 base seed 数量。
- `initial_candidate_count`：只按主观测生成的初始候选数量。
- `filtering_stats`：每条观测过滤掉的候选数量。
- `diagnostics`：主观测、目标 offset、target counter 等调试信息。
