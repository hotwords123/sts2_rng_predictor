from __future__ import annotations

import argparse
import random
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sts2_rng_predictor.rng_compat import (
    MBIG,
    derived_seed,
    deterministic_hash_code,
    internal_sample_from_derived_u32,
    uint32,
)

Q = 2**32


def parse_offset_atom(value: str) -> int:
    try:
        return uint32(int(value, 0))
    except ValueError:
        return uint32(deterministic_hash_code(value))


def parse_offset(value: str) -> int:
    expression = re.sub(r"\s+", "", value)
    if not expression:
        raise ValueError("offset expression is empty")

    total = 0
    position = 0
    for match in re.finditer(r"([+-]?)([^+-]+)", expression):
        if match.start() != position:
            raise ValueError(f"invalid offset expression: {value!r}")
        sign_text, atom = match.groups()
        sign = -1 if sign_text == "-" else 1
        total += sign * parse_offset_atom(atom)
        position = match.end()

    if position != len(expression):
        raise ValueError(f"invalid offset expression: {value!r}")
    return uint32(total)


def branch_for_seed(seed: int) -> str:
    if 0 <= seed < MBIG:
        return "+"
    if MBIG + 3 <= seed < Q:
        return "-"
    return "B"


def branch_label(base_seed: int, offset_a: int, offset_b: int) -> str:
    z_a = derived_seed(base_seed, offset_a)
    z_b = derived_seed(base_seed, offset_b)
    sign_a = branch_for_seed(z_a)
    sign_b = branch_for_seed(z_b)
    if sign_a == "B" or sign_b == "B":
        return "boundary"
    delta_q = uint32(offset_b - offset_a)
    wrap = 1 if z_a + delta_q >= Q else 0
    return f"{sign_a}{sign_b} w{wrap}"


def sample_base_seeds(
    count: int,
    *,
    start: int,
    step: int | None,
    random_seed: int | None,
) -> list[int]:
    if count <= 0:
        raise ValueError("sample count must be positive")
    if random_seed is not None:
        rng = random.Random(random_seed)
        return [rng.randrange(Q) for _ in range(count)]
    stride = step if step is not None else max(1, Q // count)
    return [uint32(start + i * stride) for i in range(count)]


def tick_label(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def save_plot(
    points: list[tuple[int, int, str]],
    *,
    offset_a_label: str,
    offset_b_label: str,
    offset_a: int,
    offset_b: int,
    counter_a: int,
    counter_b: int,
    output: Path,
    dpi: int,
    figsize: tuple[float, float],
    point_radius: float,
    opacity: float,
    color_by_branch: bool,
) -> None:
    title = (
        f"Raw sample scatter: {offset_a_label} counter {counter_a} vs "
        f"{offset_b_label} counter {counter_b}"
    )
    subtitle = f"x offset={offset_a}  y offset={offset_b}  samples={len(points)}"

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.set_title(title, fontsize=11, pad=26)
    ax.text(
        0.5,
        1.025,
        subtitle,
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=8,
        color="#52606d",
    )
    ax.set_facecolor("#fbfcfd")

    if color_by_branch:
        branches = sorted(set(branch for _, _, branch in points))
        for label in branches:
            branch_points = [
                (x / MBIG, y / MBIG) for x, y, branch in points if branch == label
            ]
            xs, ys = zip(*branch_points)
            ax.scatter(xs, ys, s=point_radius, alpha=opacity, linewidths=0, label=label)
        ax.legend(
            loc="upper left", fontsize=7, frameon=True, framealpha=0.88, markerscale=4
        )
    else:
        xs = [x / MBIG for x, _, _ in points]
        ys = [y / MBIG for _, y, _ in points]
        ax.scatter(xs, ys, s=point_radius, c="#1f2933", alpha=opacity, linewidths=0)

    tick_values = [0.0, 0.25, 0.5, 0.75, 1.0]
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks(tick_values, [tick_label(value) for value in tick_values])
    ax.set_yticks(tick_values, [tick_label(value) for value in tick_values])
    ax.set_xlabel("x raw sample / M")
    ax.set_ylabel("y raw sample / M")
    ax.grid(True, color="#d9e2ec", linewidth=0.8)
    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout(pad=0.7)
    fig.savefig(output)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sample STS2 raw RNG outputs for two offset/counter streams and draw a scatter plot."
    )
    parser.add_argument(
        "offset_a",
        help='x-axis RNG offset expression: integer, hex integer, hash token, or sums like "1+transformations"',
    )
    parser.add_argument(
        "offset_b",
        help='y-axis RNG offset expression: integer, hex integer, hash token, or sums like "1+transformations"',
    )
    parser.add_argument(
        "--counter",
        type=int,
        default=0,
        help="counter used for both streams unless overridden",
    )
    parser.add_argument("--counter-a", type=int, help="x-axis stream counter")
    parser.add_argument("--counter-b", type=int, help="y-axis stream counter")
    parser.add_argument(
        "--samples", type=int, default=20_000, help="number of base seeds to sample"
    )
    parser.add_argument(
        "--seed-start",
        type=lambda value: uint32(int(value, 0)),
        default=0,
        help="first base seed for strided sampling",
    )
    parser.add_argument(
        "--seed-step",
        type=lambda value: uint32(int(value, 0)),
        help="base seed stride; defaults to floor(2^32 / samples)",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        help="sample random base seeds with this deterministic seed",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/raw-scatter.png"),
        help="output image path",
    )
    parser.add_argument("--dpi", type=int, default=160, help="matplotlib figure DPI")
    parser.add_argument(
        "--fig-width", type=float, default=8.0, help="matplotlib figure width in inches"
    )
    parser.add_argument(
        "--fig-height",
        type=float,
        default=7.5,
        help="matplotlib figure height in inches",
    )
    parser.add_argument(
        "--point-radius", type=float, default=2.0, help="scatter point area in points^2"
    )
    parser.add_argument(
        "--opacity", type=float, default=0.75, help="scatter point opacity"
    )
    parser.add_argument(
        "--single-color",
        action="store_true",
        help="draw all points in one color instead of branch colors",
    )
    args = parser.parse_args()

    offset_a = parse_offset(args.offset_a)
    offset_b = parse_offset(args.offset_b)
    counter_a = args.counter if args.counter_a is None else args.counter_a
    counter_b = args.counter if args.counter_b is None else args.counter_b
    if counter_a < 0 or counter_b < 0:
        raise ValueError("counters must be non-negative")

    base_seeds = sample_base_seeds(
        args.samples,
        start=args.seed_start,
        step=args.seed_step,
        random_seed=args.random_seed,
    )

    points: list[tuple[int, int, str]] = []
    for base_seed in base_seeds:
        raw_a = internal_sample_from_derived_u32(
            derived_seed(base_seed, offset_a), counter_a
        )
        raw_b = internal_sample_from_derived_u32(
            derived_seed(base_seed, offset_b), counter_b
        )
        points.append((raw_a, raw_b, branch_label(base_seed, offset_a, offset_b)))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_plot(
        points,
        offset_a_label=args.offset_a,
        offset_b_label=args.offset_b,
        offset_a=offset_a,
        offset_b=offset_b,
        counter_a=counter_a,
        counter_b=counter_b,
        output=args.output,
        dpi=args.dpi,
        figsize=(args.fig_width, args.fig_height),
        point_radius=args.point_radius,
        opacity=args.opacity,
        color_by_branch=not args.single_color,
    )

    print(f"Wrote {args.output}")
    print(f"offset_a={offset_a} counter_a={counter_a}")
    print(f"offset_b={offset_b} counter_b={counter_b}")
    print(f"samples={len(points)}")


if __name__ == "__main__":
    main()
