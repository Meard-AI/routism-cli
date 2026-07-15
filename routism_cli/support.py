"""Support report builder (redacted) for operator diagnostics."""

from __future__ import annotations

import json
import platform
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List

from . import __version__
from .docker_ops import check_docker
from .engine_models import load_engine_tags
from .ollama_ops import check_ollama
from .util import find_repo_root, which

_RTM = re.compile(r"rtm_[A-Za-z0-9_\-]+")


def redact_secrets(text: str) -> str:
    """Redact rtm_ API keys; UTF-8 safe (string ops only)."""
    return _RTM.sub("rtm_***", text)


def build_support_report(root: Path | None = None) -> str:
    try:
        repo = root or find_repo_root()
        root_err = None
    except Exception as e:
        repo = None
        root_err = str(e)

    d = check_docker(quiet=True)
    o = check_ollama(quiet=True)
    tags: List[str] = []
    if repo is not None:
        tags = load_engine_tags(repo, quiet=True)

    report: Dict[str, Any] = {
        "routism_cli": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "repo_root": str(repo) if repo else None,
        "repo_error": root_err,
        "binaries": {
            "python3": which("python3") or shutil.which("python3"),
            "docker": d.docker_bin,
            "ollama": o.binary,
            "compose": " ".join(d.compose_argv) if d.compose_argv else None,
        },
        "docker": {
            "daemon_ok": d.daemon_ok,
            "messages": d.messages or [],
        },
        "ollama": {
            "reachable": o.reachable,
            "model_count": len(o.models),
            "messages": o.messages or [],
        },
        "engine_tags": tags,
    }
    raw = json.dumps(report, indent=2, sort_keys=True)
    return redact_secrets(raw)
