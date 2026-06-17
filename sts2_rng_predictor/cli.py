from __future__ import annotations

import argparse

from .core import run_example, run_same_counter_example, run_self_test


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Predict STS2 correlated RNG outputs from observed RNG call ranges."
    )
    parser.add_argument("--self-test", action="store_true", help="run built-in tests")
    parser.add_argument("--example", action="store_true", help="run a synthetic prediction example")
    parser.add_argument("--same-counter-example", action="store_true", help="run a same-counter conditional example")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
    elif args.example:
        run_example()
    elif args.same_counter_example:
        run_same_counter_example()
    else:
        parser.print_help()
