"""Terminal UI (menu-driven) for Routism operator actions. No GUI/Tauri."""

from __future__ import annotations

import sys
from typing import Callable, List, Optional, Tuple

from . import __version__
from .config_env import agent_env_snippet
from . import compose as compose_ops
from .doctor import run_doctor
from .engine_models import load_engine_tags, unique_tags
from .env_ops import set_env_key, show_env
from .ollama_ops import ensure_models, ensure_ollama, pull_json_enabled
from .probes import probe_all
from .support import build_support_report
from .util import (
    API_MODELS_URL,
    UI_URL,
    CliError,
    find_repo_root,
    ok,
    open_url,
    print_json,
    which,
)


Action = Tuple[str, str, Callable[[], int]]


def _pause() -> None:
    if not sys.stdin.isatty():
        return
    try:
        input("\n  Press Enter to continue… ")
    except EOFError:
        pass


def _banner() -> None:
    print()
    print("  ╔══════════════════════════════════════════╗")
    print(f"  ║  Routism TUI  v{__version__:<24}║")
    print("  ║  Operator console (terminal, not GUI)    ║")
    print("  ╚══════════════════════════════════════════╝")
    print()


def _safe_root():
    try:
        return find_repo_root()
    except CliError as e:
        print(f"  ! {e}", file=sys.stderr)
        return None


def act_doctor() -> int:
    return run_doctor(as_json=False)


def act_status() -> int:
    root = _safe_root()
    if root is None:
        return 1
    return compose_ops.ps(root)


def act_status_json() -> int:
    return compose_ops.status_json()


def act_start() -> int:
    from .main import cmd_start
    import argparse

    return cmd_start(argparse.Namespace())


def act_stop() -> int:
    from .main import cmd_stop
    import argparse

    return cmd_stop(argparse.Namespace())


def act_restart() -> int:
    from .main import cmd_restart
    import argparse

    return cmd_restart(argparse.Namespace())


def act_logs() -> int:
    root = _safe_root()
    if root is None:
        return 1
    return compose_ops.logs(root, follow=False, service=None)


def act_pull() -> int:
    root = _safe_root()
    if root is None:
        return 1
    ensure_ollama(yes=True, dry_run=False)
    tags = unique_tags(load_engine_tags(root, quiet=True))
    ensure_models(tags, dry_run=False, skip_pull=False, json_progress=False)
    return 0


def act_open() -> int:
    open_url(UI_URL)
    return 0


def act_binaries() -> int:
    print_json(
        {
            "python3": which("python3"),
            "docker": which("docker"),
            "ollama": which("ollama"),
        }
    )
    return 0


def act_env_show() -> int:
    root = _safe_root()
    if root is None:
        return 1
    print_json(show_env(root))
    return 0


def act_env_set() -> int:
    """Interactive allowlisted KEY=VALUE set (parity with ``routism env set``)."""
    root = _safe_root()
    if root is None:
        return 1
    from .env_ops import ALLOWLIST, parse_kv

    print("  Allowlisted keys:", ", ".join(sorted(ALLOWLIST)))
    if not sys.stdin.isatty():
        print("  Non-interactive: use  routism env set KEY=VALUE", file=sys.stderr)
        return 2
    try:
        raw = input("  KEY=VALUE> ").strip()
    except EOFError:
        return 1
    if not raw:
        print("  Cancelled.")
        return 0
    try:
        k, v = parse_kv(raw)
        set_env_key(root, k, v)
        print_json(show_env(root))
        return 0
    except CliError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.code


def act_support() -> int:
    print(build_support_report())
    return 0


def act_agent_env() -> int:
    print(agent_env_snippet())
    return 0


def act_probe() -> int:
    print_json(probe_all())
    return 0


def act_setup() -> int:
    from .main import cmd_setup
    import argparse

    return cmd_setup(
        argparse.Namespace(yes=False, dry_run=False, skip_pull=False, skip_docker=False)
    )


def act_version() -> int:
    print(f"routism {__version__}")
    return 0


MENU: List[Action] = [
    ("1", "Setup / first-run wizard", act_setup),
    ("2", "Doctor (health checks)", act_doctor),
    ("3", "Status (compose ps)", act_status),
    ("4", "Status JSON", act_status_json),
    ("5", "Start stack", act_start),
    ("6", "Stop stack", act_stop),
    ("7", "Restart stack", act_restart),
    ("8", "Logs (api+ui tail)", act_logs),
    ("9", "Pull engine models", act_pull),
    ("a", "Open dashboard", act_open),
    ("b", "Binaries on PATH", act_binaries),
    ("c", "Env show (allowlisted)", act_env_show),
    ("s", "Env set KEY=VALUE (allowlisted)", act_env_set),
    ("d", "Support report", act_support),
    ("e", "Agent env snippet", act_agent_env),
    ("f", "HTTP probes (api/ui/health)", act_probe),
    ("v", "Version", act_version),
    ("q", "Quit", lambda: 0),
]


def run_tui(*, once: Optional[str] = None, smoke: bool = False) -> int:
    """
    Interactive menu TUI. ``smoke=True`` prints banner + menu and exits 0
    (for headless verification). ``once`` is a menu key to run single action.
    """
    _banner()
    print(f"  API models: {API_MODELS_URL}")
    print(f"  Dashboard:  {UI_URL}")
    print()

    if smoke:
        print("  [smoke] TUI entry OK — menu actions available:")
        for key, label, _ in MENU:
            print(f"    [{key}] {label}")
        print("  [smoke] exit")
        return 0

    if once is not None:
        for key, label, fn in MENU:
            if key == once:
                print(f"  → {label}")
                try:
                    return fn()
                except CliError as e:
                    print(f"error: {e}", file=sys.stderr)
                    return e.code
        print(f"Unknown menu key: {once}", file=sys.stderr)
        return 2

    if not sys.stdin.isatty():
        print(
            "  Non-interactive stdin. Use: routism tui --smoke  or  routism tui --once KEY",
            file=sys.stderr,
        )
        return 2

    while True:
        print("  ── Actions ─────────────────────────────")
        for key, label, _ in MENU:
            print(f"   [{key}]  {label}")
        print()
        try:
            choice = input("  Select> ").strip().lower()
        except EOFError:
            print()
            return 0
        if choice in ("q", "quit", "exit"):
            ok("Bye")
            return 0
        matched = False
        for key, label, fn in MENU:
            if choice == key:
                matched = True
                print()
                print(f"  → {label}")
                try:
                    code = fn()
                    if code:
                        print(f"  (exit {code})", file=sys.stderr)
                except CliError as e:
                    print(f"error: {e}", file=sys.stderr)
                except KeyboardInterrupt:
                    print("\nInterrupted.", file=sys.stderr)
                _pause()
                print()
                break
        if not matched:
            print("  Unknown choice. Try again.")
            print()
