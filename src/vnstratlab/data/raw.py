"""Raw snapshots: one Parquet file per (source, run_id), written before normalisation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from vnstratlab.data.protocol import SourceError

if TYPE_CHECKING:
    from vnstratlab.paths import AppPaths


def snapshot_path(paths: AppPaths, source: str, run_id: str) -> Path:
    return paths.raw_dir / source / f"{run_id}.parquet"


def write_raw(paths: AppPaths, source: str, run_id: str, frame: pd.DataFrame) -> Path:
    """Write the source frame exactly as received; returns the file path.

    The file is created exclusively: an existing snapshot is never overwritten.
    """
    path = snapshot_path(paths, source, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = path.open("xb")
    except FileExistsError:
        raise SourceError(
            f"raw snapshot {path.name} already exists; refusing to overwrite"
        ) from None
    try:
        with handle:
            frame.to_parquet(handle, index=False)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def read_raw(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)
