"""Docker Compose operations for the Routism stack."""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

from .docker_ops import DockerStatus, check_docker, compose_cmd, require_docker
from .util import (
    API_MODELS_URL,
    UI_URL,
    CliError,
    http_get,
    info,
    ok,
    run,
    warn,
)

# Path used by status collectors (re-exported typing)


def _status_for_compose(*, dry_run: bool = False) -> DockerStatus:
    """Require full Docker health unless dry-run (then CLI + compose binary is enough)."""
    if not dry_run:
        return require_docker()
    status = check_docker(quiet=True)
    if status.compose_argv:
        return status
    # Fall back to a synthetic argv so dry-run can still print the command
    status.compose_argv = ["docker", "compose"]
    warn("Docker Compose not detected; dry-run will show a generic compose command")
    return status


def up(repo_root: Path, *, dry_run: bool = False, build: bool = True) -> None:
    status = _status_for_compose(dry_run=dry_run)
    args = ["up", "--build", "-d"] if build else ["up", "-d"]
    cmd = compose_cmd(status, *args)
    info(f"Starting stack: {' '.join(cmd)}")
    run(cmd, cwd=repo_root, check=True, dry_run=dry_run)
    if not dry_run:
        ok("docker compose up finished")


def down(repo_root: Path, *, dry_run: bool = False) -> None:
    status = _status_for_compose(dry_run=dry_run)
    cmd = compose_cmd(status, "down")
    info(f"Stopping stack: {' '.join(cmd)}")
    run(cmd, cwd=repo_root, check=True, dry_run=dry_run)
    if not dry_run:
        ok("Stack stopped")


def restart(repo_root: Path, *, dry_run: bool = False) -> None:
    status = _status_for_compose(dry_run=dry_run)
    cmd = compose_cmd(status, "restart")
    info(f"Restarting stack: {' '.join(cmd)}")
    run(cmd, cwd=repo_root, check=True, dry_run=dry_run)
    if not dry_run:
        ok("Stack restarted")


def ps(repo_root: Path) -> int:
    status = require_docker()
    cmd = compose_cmd(status, "ps")
    cp = run(cmd, cwd=repo_root, check=False)
    return cp.returncode


def logs(
    repo_root: Path,
    *,
    follow: bool = False,
    service: Optional[str] = None,
) -> int:
    status = require_docker()
    args: List[str] = ["logs"]
    if follow:
        args.append("-f")
    # sensible tail so first view is useful
    args.extend(["--tail", "200"])
    if service:
        args.append(service)
    cmd = compose_cmd(status, *args)
    cp = run(cmd, cwd=repo_root, check=False)
    return cp.returncode


def collect_status_report(repo_root: Optional[Path] = None) -> dict:
    """Machine-readable status (compose + endpoints). Safe when Docker is down."""
    from .util import find_repo_root

    messages: list = []
    root: Optional[Path] = None
    try:
        root = repo_root or find_repo_root()
    except Exception as e:
        return {
            "ok": False,
            "repo_root": None,
            "compose": {"available": False, "services": {}, "messages": [str(e)]},
            "endpoints": {"api": False, "ui": False},
            "pool": {"size": None},
            "messages": [str(e)],
        }

    status = check_docker(quiet=True)
    services: dict = {}
    available = bool(status.compose_argv and status.daemon_ok)
    stack_up = False
    if available and status.compose_argv:
        try:
            cmd = compose_cmd(status, "ps", "--format", "json")
            cp = run(cmd, cwd=root, check=False, capture=True)
            raw = (cp.stdout or "").strip()
            # docker compose ps --format json: one object per line (NDJSON) or array
            import json as _json

            rows = []
            if raw.startswith("["):
                rows = _json.loads(raw)
            else:
                for line in raw.splitlines():
                    line = line.strip()
                    if line:
                        rows.append(_json.loads(line))
            for row in rows:
                name = row.get("Service") or row.get("Name") or row.get("service") or "?"
                state = row.get("State") or row.get("Status") or ""
                services[str(name)] = {"state": state, "raw": row}
                if "running" in str(state).lower():
                    stack_up = True
        except Exception as e:
            messages.append(f"compose ps failed: {e}")
            available = False
    else:
        messages.extend(status.messages or ["Docker not available"])

    api_code, _ = http_get(API_MODELS_URL, timeout=2.0)
    ui_code, _ = http_get(UI_URL, timeout=2.0)
    api_up = api_code == 200
    ui_up = bool(ui_code and ui_code < 500)
    if api_up:
        stack_up = True

    pool_size = None
    try:
        # Optional management metrics if exposed without auth
        code, body = http_get("http://127.0.0.1:8000/v1/metrics", timeout=2.0)
        if code == 200 and body:
            import json as _json

            data = _json.loads(body)
            if isinstance(data, dict) and "pool" in data:
                p = data["pool"]
                if isinstance(p, dict) and "size" in p:
                    pool_size = p["size"]
                elif isinstance(p, list):
                    pool_size = len(p)
    except Exception:
        pass

    return {
        "ok": available and (api_up or stack_up),
        "repo_root": str(root),
        "compose": {
            "available": available,
            "services": services,
            "stack_up": stack_up,
            "messages": messages,
        },
        "endpoints": {
            "api": api_up,
            "api_status": api_code,
            "ui": ui_up,
            "ui_status": ui_code,
            "api_url": API_MODELS_URL,
            "ui_url": UI_URL,
        },
        "pool": {"size": pool_size},
        "milestones": {
            "stack_up": bool(api_up),
            "agent_ready": bool(pool_size and pool_size >= 1),
        },
        "messages": messages,
    }


def status_json(repo_root: Optional[Path] = None) -> int:
    from .util import emit_mode, print_json

    with emit_mode(quiet=True, human_to_stderr=True):
        report = collect_status_report(repo_root)
    print_json(report)
    return 0 if report.get("ok") else 1


def wait_for_api(*, timeout_s: float = 180.0, interval_s: float = 2.0) -> bool:
    """Poll GET /v1/models until HTTP 200."""
    info(f"Waiting up to {int(timeout_s)}s for API at {API_MODELS_URL}…")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        code, _ = http_get(API_MODELS_URL, timeout=3.0)
        if code == 200:
            ok(f"API healthy: {API_MODELS_URL}")
            return True
        time.sleep(interval_s)
    return False


def smoke_check() -> None:
    code, body = http_get(API_MODELS_URL, timeout=5.0)
    if code != 200:
        raise CliError(
            f"Smoke check failed: {API_MODELS_URL} returned HTTP {code or 'connection error'}"
        )
    ok(f"Smoke check passed (GET /v1/models → {code})")
    info(f"Dashboard: {UI_URL}")
    info(f"API:       http://localhost:8000")
