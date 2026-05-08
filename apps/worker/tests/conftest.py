from __future__ import annotations

import sys
from pathlib import Path


def _prepend_sys_path(p: Path) -> None:
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)


# When running `pytest` from the repo root, `apps/worker` isn't on sys.path by default.
# The worker code also imports modules from `apps/api` and shared code from `packages/`.
_repo_root = Path(__file__).resolve().parents[3]
_prepend_sys_path(_repo_root / "apps" / "worker")
_prepend_sys_path(_repo_root / "apps" / "api")
_prepend_sys_path(_repo_root / "packages")

