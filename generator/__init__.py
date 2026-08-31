"""Policy Time Machine synthetic data generator.

Produces the seven source tables of `docs/specs/01-data-model-and-synthetic-data.md`
section 3 from a seed and an anchor date. The dataset is entirely synthetic; no
real data and no personal information are involved at any point.
"""

from .build import build

__all__ = ["build"]
