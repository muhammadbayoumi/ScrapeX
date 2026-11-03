"""Where a name lands under a folder: one question, asked of every name we are handed."""
from __future__ import annotations

import os
from pathlib import Path


def name_inside(folder: Path | str, name: str) -> Path:
    """`folder / name`, or a ValueError unless that lands inside `folder`.

    REALPATH, THEN STARTSWITH, IN THAT ORDER: it follows links as `Path.resolve` does,
    and it is the one shape code scanning reads as a guard (#1935). The prefix keeps its
    trailing separator, so a sibling folder whose name merely begins the same is refused.
    """
    root = os.path.join(os.path.realpath(folder), "")
    target = os.path.realpath(os.path.join(root, name))
    if not target.startswith(root):
        raise ValueError(f"{name!r} would land outside {folder}")
    return Path(target)
