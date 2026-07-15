"""Locate or clone the official Routism product repo (standalone CLI)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .util import COMPOSE_FILE, ORCH_MARKER, CliError, info, ok

PRODUCT_REPO_URL = os.environ.get(
    "ROUTISM_PRODUCT_GIT",
    "https://github.com/Meard-AI/Routism.git",
)


def is_product_root(path: Path) -> bool:
    return (path / COMPOSE_FILE).is_file() and (path / ORCH_MARKER).is_file()


def default_product_dir() -> Path:
    env = (os.environ.get("ROUTISM_HOME") or "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / "Routism"


def ensure_product_repo(
    *,
    dest: Optional[Path] = None,
    url: Optional[str] = None,
    dry_run: bool = False,
    quiet: bool = False,
) -> Path:
    """Ensure a local checkout of Meard-AI/Routism exists; clone if missing."""
    target = (dest or default_product_dir()).expanduser().resolve()
    repo_url = (url or PRODUCT_REPO_URL).strip()

    if is_product_root(target):
        os.environ["ROUTISM_HOME"] = str(target)
        if not quiet:
            ok(f"Product stack root: {target}")
        return target

    if target.exists() and any(target.iterdir()):
        raise CliError(
            f"{target} exists but is not a Routism stack root "
            f"(need {COMPOSE_FILE} + {ORCH_MARKER}).\n"
            f"  Point ROUTISM_HOME at a clone of {PRODUCT_REPO_URL}\n"
            f"  or remove the directory and re-run: routism install"
        )

    git = shutil.which("git")
    if not git:
        raise CliError("git not found on PATH; cannot clone Routism product repo")

    if dry_run:
        if not quiet:
            info(f"[dry-run] would clone {repo_url} → {target}")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    if not quiet:
        info(f"Cloning product from {repo_url}")
        info(f"  → {target}")
    try:
        subprocess.run(
            [git, "clone", "--depth", "1", repo_url, str(target)],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise CliError(f"git clone failed ({e.returncode}): {repo_url}") from e

    if not is_product_root(target):
        raise CliError(
            f"Clone finished but stack markers missing under {target}.\n"
            f"  Check that {repo_url} is the official Routism monorepo."
        )

    os.environ["ROUTISM_HOME"] = str(target)
    if not quiet:
        ok(f"Installed product checkout at {target}")
    return target


def product_status() -> dict:
    target = default_product_dir().resolve()
    return {
        "ROUTISM_HOME_env": (os.environ.get("ROUTISM_HOME") or "").strip() or None,
        "default_dir": str(target),
        "exists": target.is_dir(),
        "is_stack_root": is_product_root(target) if target.is_dir() else False,
        "product_git": PRODUCT_REPO_URL,
    }
