"""Health checks for Docker, Ollama, engine models, and stack endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .docker_ops import check_docker
from .engine_models import load_engine_tags
from .ollama_ops import _model_match, check_ollama
from .util import (
    API_MODELS_URL,
    UI_URL,
    emit_mode,
    fail,
    find_repo_root,
    http_get,
    info,
    ok,
    print_json,
    warn,
)


def collect_doctor_report(root: Optional[Path] = None) -> Dict[str, Any]:
    """Build a machine-readable doctor report (no prints)."""
    messages: List[str] = []
    errors = 0
    warnings = 0
    repo: Optional[str] = None
    try:
        r = root or find_repo_root()
        repo = str(r)
    except Exception as e:
        messages.append(str(e))
        return {
            "ok": False,
            "version": __version__,
            "repo_root": None,
            "docker": {"ok": False},
            "ollama": {"ok": False},
            "engine": {"tags": [], "missing": [], "ok": False},
            "endpoints": {"api": False, "ui": False},
            "errors": 1,
            "warnings": 0,
            "messages": messages,
        }

    rpath = Path(repo)
    d = check_docker(quiet=True)
    o = check_ollama(quiet=True)
    docker_ok = bool(d.docker_bin and d.compose_argv and d.daemon_ok)
    ollama_ok = bool(o.binary and o.reachable)
    if not docker_ok:
        errors += 1
        messages.extend(d.messages or ["Docker not ready"])
    if not ollama_ok:
        errors += 1
        messages.extend(o.messages or ["Ollama not ready"])

    tags = load_engine_tags(rpath, quiet=True)
    missing: List[str] = []
    if o.reachable:
        missing = [t for t in tags if not _model_match(o.models, t)]
        if missing:
            warnings += 1
            messages.append(f"Missing engine models: {', '.join(missing)}")
    else:
        warnings += 1
        messages.append("Skipping model inventory (Ollama API down)")

    api_code, _ = http_get(API_MODELS_URL, timeout=2.0)
    ui_code, _ = http_get(UI_URL, timeout=2.0)
    api_up = api_code == 200
    ui_up = bool(ui_code and ui_code < 500)

    return {
        "ok": errors == 0,
        "version": __version__,
        "repo_root": repo,
        "docker": {
            "ok": docker_ok,
            "daemon_ok": d.daemon_ok,
            "docker_bin": d.docker_bin,
            "compose": " ".join(d.compose_argv) if d.compose_argv else None,
        },
        "ollama": {
            "ok": ollama_ok,
            "binary": o.binary,
            "reachable": o.reachable,
            "model_count": len(o.models),
        },
        "engine": {
            "tags": tags,
            "missing": missing,
            "ok": o.reachable and not missing,
        },
        "endpoints": {
            "api": api_up,
            "api_status": api_code,
            "ui": ui_up,
            "ui_status": ui_code,
        },
        "errors": errors,
        "warnings": warnings,
        "messages": messages,
    }


def run_doctor(*, as_json: bool = False) -> int:
    if as_json:
        with emit_mode(quiet=True, human_to_stderr=True):
            report = collect_doctor_report()
        print_json(report)
        return 0 if report.get("ok") else 1

    print(f"Routism doctor v{__version__}")
    errors = 0
    warnings = 0

    print("\nRepo")
    try:
        root = find_repo_root()
        ok(f"repo root: {root}")
    except Exception as e:
        fail(str(e))
        return 1

    print("\nDocker")
    d = check_docker(quiet=False)
    if not d.docker_bin or not d.compose_argv or not d.daemon_ok:
        errors += 1

    print("\nOllama")
    o = check_ollama(quiet=False)
    if not o.binary or not o.reachable:
        errors += 1

    print("\nEngine models")
    tags = load_engine_tags(root, verbose=True)
    if o.reachable:
        missing = [t for t in tags if not _model_match(o.models, t)]
        if missing:
            warn(f"Missing engine models: {', '.join(missing)}")
            info("Run:  routism pull-engine")
            warnings += 1
        else:
            ok(f"All engine tags present: {', '.join(tags)}")
    else:
        warn("Skipping model inventory (Ollama API down)")
        warnings += 1

    print("\nConfig")
    env_path = root / ".env"
    if env_path.is_file():
        ok(".env exists")
        text = env_path.read_text(encoding="utf-8")
        if "OLLAMA_BASE_URL" in text:
            ok("OLLAMA_BASE_URL mentioned in .env")
        else:
            warn("OLLAMA_BASE_URL not set in .env (setup will add it)")
            warnings += 1
    else:
        warn(".env missing (will be created from .env.example on setup)")
        warnings += 1

    compose = root / "docker-compose.yml"
    if compose.is_file():
        ctext = compose.read_text(encoding="utf-8")
        if "host.docker.internal" in ctext and "OLLAMA_BASE_URL" in ctext:
            ok("docker-compose.yml wires OLLAMA_BASE_URL + host-gateway")
        else:
            warn("docker-compose.yml may be missing OLLAMA_BASE_URL / extra_hosts")
            warnings += 1

    print("\nStack endpoints")
    code, _ = http_get(API_MODELS_URL, timeout=2.0)
    if code == 200:
        ok(f"API up: {API_MODELS_URL}")
    else:
        info(f"API not up yet ({API_MODELS_URL}) — run: routism start")

    ui_code, _ = http_get(UI_URL, timeout=2.0)
    if ui_code and ui_code < 500:
        ok(f"UI responding: {UI_URL} (HTTP {ui_code})")
    else:
        info(f"UI not up yet ({UI_URL})")

    print()
    if errors:
        fail(f"doctor: {errors} error(s), {warnings} warning(s)")
        return 1
    if warnings:
        warn(f"doctor: OK with {warnings} warning(s)")
        return 0
    ok("doctor: all checks passed")
    return 0
