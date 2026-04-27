"""Robust file/folder copy operations."""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Optional

from app.logger import logger


def _wait_stable(
    path: Path,
    timeout: float = 30.0,
    interval: float = 1.0,
) -> bool:
    """
    Wait until *path* stops changing in size (i.e. upload/write is complete).
    Returns True if the file stabilised before *timeout*, False otherwise.
    """
    deadline = time.monotonic() + timeout
    prev_size: int = -1

    while time.monotonic() < deadline:
        try:
            cur_size = path.stat().st_size
        except OSError:
            time.sleep(interval)
            continue

        if cur_size == prev_size and cur_size >= 0:
            return True

        prev_size = cur_size
        time.sleep(interval)

    return False


def _unique_dest(dest: Path) -> Path:
    """
    Return *dest* if it doesn't exist, otherwise append `` (1)``, `` (2)`` … until
    a free name is found.
    """
    if not dest.exists():
        return dest

    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    counter = 1

    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def copy_item(
    src: Path,
    dest_dir: Path,
    preserve_timestamps: bool = True,
) -> Optional[Path]:
    """
    Copy *src* (file or directory) into *dest_dir*.

    * Never overwrites – generates unique suffix if target exists.
    * For files, waits until the file stabilises before copying.
    * Copies directory trees recursively.
    * Preserves timestamps when *preserve_timestamps* is True.

    Returns the final destination path, or ``None`` on failure.
    """
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error(f"Cannot create destination directory {dest_dir}: {exc}")
        return None

    dest = _unique_dest(dest_dir / src.name)

    try:
        if src.is_dir():
            logger.info(f"Copying folder  {src}  →  {dest}")
            shutil.copytree(str(src), str(dest))
        else:
            if not _wait_stable(src):
                logger.warning(
                    f"File {src.name!r} did not stabilise within timeout – copying anyway."
                )
            logger.info(f"Copying file  {src}  →  {dest}")
            if preserve_timestamps:
                shutil.copy2(str(src), str(dest))
            else:
                shutil.copy(str(src), str(dest))

        return dest

    except Exception as exc:
        logger.error(f"Copy failed  {src}  →  {dest}: {exc}")
        return None
