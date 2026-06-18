# STS2 RNG 相关性计算器

这份工具用于分析 STS2 中“同一基础 seed + 不同固定偏移”的 RNG 相关性。实现位于 `sts2_rng_predictor/` 包中，既可以作为 Python 库导入，也可以直接运行内置示例和自测。

更完整的数学建模见 [rng-math-model.md](rng-math-model.md)。

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
uv run sts2-rng-predictor --self-test
uv run sts2-rng-predictor --example
uv run sts2-rng-predictor --same-counter-example
uv run python scripts/reproduce_leafy_hefty.py
uv run python scripts/reproduce_trash_heap.py --sample-check 1000000
uv run python scripts/reproduce_trash_heap.py --multiplayer --net-id 76561198000000000
```

项目现在按 Python package 组织，`pyproject.toml` 使用 `setuptools.build_meta`，
`[tool.uv] package = true`。`scripts/` 下的复现脚本仍保留在包外，但通过已安装
package 导入 `sts2_rng_predictor`，不需要手动改 `PYTHONPATH`。

源代码/本地化路径由项目根目录 `.env` 提供：

```dotenv
STS2_CODE_ROOT=/path/to/sts2/code
STS2_LOCALIZATION_ROOT=/path/to/sts2/localization
```

也可以调用 `load_local_source_config(path_to_env)` 显式读取其它 `.env` 文件。

作为库导入：

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

如果所有观测和目标调用使用相同 counter，优先使用 same-counter 预测器：

```python
same_counter_observations = [
    IntObservation("monster_ai", 0, IntCall(0, 1_000_000), 123456, 123456),
    IntObservation("shuffle", 0, IntCall(0, 1_000_000), 654321, 654321),
]

result = predict_same_counter_fast(
    same_counter_observations,
    IntTarget("niche", 0, IntCall(0, 10)),
)
```

它会选择 raw sample 空间最小的观测作为锚点，但不枚举 raw sample，也不保存完整 base seed 集合；同 counter 下每个 branch 都退化为 sample 空间的平移或反射，剩余计数用 floor-sum 精确完成。
目标 `NextInt` range 默认最多输出 100,000 个桶；如果确实需要更大的完整分布，可以传 `max_target_buckets=` 提高上限。

`predict_same_counter_distribution()` 是旧的流式枚举对照实现，主要用于测试和调试。

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

事件 RNG 不是 snake-case 命名 RNG。`EventModel.BeginEvent` 使用：

```csharp
runSeed + (IsShared ? 0 : Owner.NetId) + GetDeterministicHashCode(event.Id.Entry)
```

单人常见 `Owner.NetId == 1`，可用 `event_offset_for_id("NEOW")`、
`event_offset_for_id("TRASH_HEAP")` 得到 `1 + hash(event id)` 的 32 位 offset。
多人预测时传入目标玩家的 net id，例如 `event_offset_for_id("TRASH_HEAP", net_id)`。

`PlayerRngSet` 也会按玩家分流。`Player.InitializeSeed` 先用：

```csharp
hash(runSeedString) + Owner.NetId
```

再由 `PlayerRngSet` 为 `Rewards`、`Transformations` 等 RNG 加上 snake-case
名称 hash。工具里的 `player_offset_for_name("rewards", net_id)` 可得到对应偏移；
单人默认同样是 `net_id=1`。

多人还会影响卡池过滤。`IRunState.CardMultiplayerConstraint` 只有两种实际分支：
单人运行过滤掉 `MultiplayerOnly` 卡，多人运行过滤掉 `SingleplayerOnly` 卡。
复现脚本默认按单人过滤；传 `--multiplayer` 时按多人过滤。

这些复现脚本里的 act 条件还假设 Underdocks epoch 已揭示，且不是单人首次发现
Underdocks 的强制分支。源码中 `ActModel.GetRandomList()` 在普通情况下用一次
`rng.NextBool()` 决定 Act 1 是 Underdocks 还是 Overgrowth；如果 Underdocks 未揭示，
或单人首次发现 Underdocks 被强制触发，这个 act 观测不能按同一个 RNG call 建模。

其它仍需按具体存档/运行状态确认的边界包括：unlock state、Neow/Ancient 是否被 hook
禁止、modifier/relic hook 对 card reward pool 的修改，以及会在目标调用前消耗同一 RNG
stream 的额外操作。

## 计数器

`counter` 是 STS2 `Rng.Counter` 在这次调用之前的值。一个全新的 RNG 第一次调用是 `counter=0`，调用后 counter 变为 1。`NextInt`、`NextFloat`、`NextItem` 都按一次调用处理；`Shuffle(n)` 需要拆成 `n - 1` 次 `NextInt`。

## 限制

- 至少需要一个 `next_int` 观测。工具用它反推候选 base seed，不做 2^32 全量扫描。
- 观测太宽时会抛出 `PredictionTooBroadError`。这通常表示需要增加观测、使用更窄区间，或显式提高 `max_candidates`。
- `predict_same_counter_fast()` 要求所有观测和目标的 `counter` 相同；它只支持 `NextInt`，返回 `SameCounterResult`。
- `predict_same_counter_distribution()` 是 same-counter 的旧流式枚举器；它使用 `max_anchor_samples` 控制锚观测 raw sample 枚举规模。
- v1 不自动推断未知 counter，也不建模完整 `Shuffle`、`NextGaussian*` 或其它会消耗多次底层随机数的组合行为。
- `next_float` 可以作为观测区间过滤；如果目标是 `next_float`，需要在 `CallSpec` 上设置 `buckets`，工具会输出分桶分布。

## 结果解读

`predict_distribution()` 返回 `PredictionResult`：

- `distribution`：目标输出到概率的后验分布。
- `candidate_count`：满足所有观测的 base seed 数量。
- `initial_candidate_count`：只按主观测生成的初始候选数量。
- `filtering_stats`：每条观测过滤掉的候选数量。
- `diagnostics`：主观测、目标 offset、target counter 等调试信息。

`predict_same_counter_fast()` 返回 `SameCounterResult`：

- `distribution`：目标整数输出到概率的后验分布。
- `counts`：目标整数输出到精确计数。
- `total_count`：满足所有观测的等价 base seed / branch 点计数。
- `diagnostics`：anchor、branch 数、边界点补计数等调试信息。
