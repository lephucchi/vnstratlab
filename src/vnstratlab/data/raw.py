"""Raw snapshots: one Parquet file per (source, run_id), written before normalisation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from vnstratlab.paths import AppPaths


def snapshot_path(paths: AppPaths, source: str, run_id: str) -> Path:
    return paths.raw_dir / source / f"{run_id}.parquet"


def write_raw(paths: AppPaths, source: str, run_id: str, frame: pd.DataFrame) -> Path:
    """Write the source frame exactly as received; returns the file path."""
    path = snapshot_path(paths, source, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def read_raw(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)
