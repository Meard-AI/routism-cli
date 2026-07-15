"""Allowlisted .env show/set for stack config (compose-honored keys)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .util import CliError, ok

# Only keys operators may set via CLI (parity with desktop settings contract).
ALLOWLIST = frozenset(
    {
        "OLLAMA_BASE_URL",
        "ROUTISM_REQUIRE_API_KEY",
        "ROUTISM_OPEN_LOCAL",
        "ROUTISM_ALLOW_ANON_LOOPBACK",
        "ROUTISM_PUBLIC_BASE_URL",
        "MANAGEMENT_API_KEY",
        "NEXT_PUBLIC_ROUTISM_API",
    }
)

_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def parse_env_file(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}
    out: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = _LINE.match(raw)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip().strip("\"'")
        out[key] = val
    return out


def show_env(repo_root: Path) -> Dict[str, Optional[str]]:
    data = parse_env_file(repo_root / ".env")
    return {k: data.get(k) for k in sorted(ALLOWLIST)}


def set_env_key(repo_root: Path, key: str, value: str) -> None:
    if key not in ALLOWLIST:
        raise CliError(
            f"Key not allowlisted: {key}\n"
            f"  Allowed: {', '.join(sorted(ALLOWLIST))}"
        )
    if key == "ROUTISM_REQUIRE_API_KEY" and value.strip() not in ("0", "1"):
        raise CliError("ROUTISM_REQUIRE_API_KEY must be 0 or 1")
    if key in ("ROUTISM_OPEN_LOCAL", "ROUTISM_ALLOW_ANON_LOOPBACK") and value.strip() not in (
        "0",
        "1",
    ):
        raise CliError(f"{key} must be 0 or 1")
    if key in ("OLLAMA_BASE_URL", "ROUTISM_PUBLIC_BASE_URL", "NEXT_PUBLIC_ROUTISM_API"):
        v = value.strip()
        if v and not (v.startswith("http://") or v.startswith("https://")):
            raise CliError(f"{key} must be an http(s) URL")

    env_path = repo_root / ".env"
    if not env_path.is_file():
        example = repo_root / ".env.example"
        if example.is_file():
            env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            env_path.write_text("# Routism .env\n", encoding="utf-8")

    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    pattern = re.compile(rf"(?m)^\s*{re.escape(key)}\s*=.*$")
    # Never pass user value as re.sub replacement template (\1 etc. would explode).
    replacement = f"{key}={value.strip()}"
    text = "".join(lines)
    if pattern.search(text):
        text = pattern.sub(lambda _m: replacement, text)
        if not text.endswith("\n"):
            text += "\n"
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += replacement + "\n"
    # atomic-ish write
    tmp = env_path.with_suffix(".env.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(env_path)
    ok(f"Set {key} in {env_path}")


def parse_kv(s: str) -> Tuple[str, str]:
    if "=" not in s:
        raise CliError("Expected KEY=VALUE")
    k, _, v = s.partition("=")
    k = k.strip()
    if not k:
        raise CliError("Empty key")
    return k, v
