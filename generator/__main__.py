"""Command line entry point.

    python -m generator --seed 42 --anchor-date YYYY-MM-DD --out data/raw

The anchor date defaults to the generation date (ADR-0006). Passing it
explicitly is what makes a regeneration reproducible; the seed owns identity,
the anchor owns dates.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from .build import build
from .emit import write


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m generator", description=__doc__)
    parser.add_argument("--seed", type=int, required=True, help="owns every identifier and story")
    parser.add_argument(
        "--anchor-date",
        type=dt.date.fromisoformat,
        default=None,
        help="UTC date the dataset is anchored to; defaults to the generation date",
    )
    parser.add_argument("--out", required=True, help="directory to write one parquet file per table")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    anchor = args.anchor_date or dt.datetime.now(dt.timezone.utc).date()
    frames = build(args.seed, anchor)
    paths = write(frames, args.out, anchor)
    print(f"seed={args.seed} anchor={anchor.isoformat()} out={args.out}")
    for path in paths:
        print(f"  {path.name:<32} {len(frames[path.stem]):>8,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
