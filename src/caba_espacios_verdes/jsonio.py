"""JSON that accepts the numpy scalars pandas and GeoPandas hand back."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def _default(value: object):
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")


def dumps(payload: object, *, indent: int | None = None) -> str:
    return json.dumps(payload, indent=indent, ensure_ascii=False, default=_default)


def write(path: Path, payload: object, *, indent: int = 2) -> None:
    path.write_text(dumps(payload, indent=indent), encoding="utf-8")
