"""Routism CLI — terminal operator surface (CLI + TUI). Bare `routism` runs setup."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import __version__
from .config_env import agent_env_snippet, ensure_ollama_base_url
from . import compose as compose_ops
from .doctor import run_doctor
from .engine_models import load_engine_tags, unique_tags
from .env_ops import parse_kv, set_env_key, show_env
from .ollama_ops import ensure_models, ensure_ollama, pull_json_enabled
from .probes import probe_all, probe_api, probe_health, probe_ui
from .support import build_support_report
from .product import PRODUCT_REPO_URL, ensure_product_repo, product_status
from .util import (
    UI_URL,
    CliError,
    confirm,
    find_repo_root,
    info,
    ok,
    open_url,
    print_json,
    step,
    warn,
    which,
)


def _require_product(*, dry_run: bool = False, quiet: bool = False):
    """Clone official product if needed; return stack root Path."""
    return ensure_product_repo(dry_run=dry_run, quiet=quiet)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="routism",
        description=(
            "routism-cli — standalone terminal operator for Routism.\n"
            "Clones and runs the product from https://github.com/Dreamstick9/Routism\n"
            "This is not a desktop GUI. Bare `routism` runs full setup."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # install this CLI (once):
  git clone https://github.com/Dreamstick9/routism-cli.git && cd routism-cli && ./install.sh

  routism install             # clone product → ~/Routism
  routism setup -y            # models + docker compose
  routism tui                 # terminal menu UI
  routism doctor --json
  routism start|stop|status
""",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"routism-cli {__version__}",
    )
    sub = p.add_subparsers(dest="command")

    inst = sub.add_parser(
        "install",
        help=f"Clone official product ({PRODUCT_REPO_URL}) if missing",
    )
    inst.add_argument(
        "--dir",
        dest="install_dir",
        default=None,
        help="Product checkout path (default: $ROUTISM_HOME or ~/Routism)",
    )
    inst.add_argument(
        "--url",
        dest="install_url",
        default=None,
        help="Git URL override (default: official Dreamstick9/Routism)",
    )
    inst.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("setup", help="Full interactive setup (default if no command)")
    s.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Non-interactive: accept defaults / install without asking",
    )
    s.add_argument("--dry-run", action="store_true", help="Show what would run, change nothing")
    s.add_argument("--skip-pull", action="store_true", help="Skip ollama pull of engine models")
    s.add_argument("--skip-docker", action="store_true", help="Skip docker compose up")

    doctor_p = sub.add_parser("doctor", help="Check Docker, Ollama, engine models, stack")
    doctor_p.add_argument("--json", action="store_true", help="Pure JSON on stdout")

    sub.add_parser("start", help="Start API + UI (docker compose up)")
    sub.add_parser("stop", help="Stop stack (docker compose down)")
    sub.add_parser("restart", help="Restart stack")
    status_p = sub.add_parser("status", help="Show container status")
    status_p.add_argument("--json", action="store_true", help="Pure JSON on stdout")

    logs = sub.add_parser("logs", help="Show container logs")
    logs.add_argument("-f", "--follow", action="store_true")
    logs.add_argument("service", nargs="?", default=None)

    pull_p = sub.add_parser("pull-engine", help="Download engine models via Ollama")
    pull_p.add_argument(
        "--json",
        "--progress-json",
        dest="json",
        action="store_true",
        help="NDJSON progress on stdout",
    )

    sub.add_parser("open", help=f"Open dashboard ({UI_URL})")
    sub.add_parser("version", help="Print version")
    sub.add_parser("binaries", help="Report docker/ollama/python3 on PATH")

    env_p = sub.add_parser("env", help="Show/set allowlisted .env keys")
    env_sub = env_p.add_subparsers(dest="env_cmd")
    env_sub.add_parser("show", help="Show allowlisted keys")
    env_set = env_sub.add_parser("set", help="Set KEY=VALUE (allowlisted)")
    env_set.add_argument("assignment", help="KEY=VALUE")

    support_p = sub.add_parser("support", help="Print redacted support report JSON")
    support_p.add_argument(
        "--copy",
        action="store_true",
        help="Also copy to clipboard when pbcopy/xclip available",
    )

    sub.add_parser("agent-env", help="Print OpenAI-compatible env snippet for agents")

    probe_p = sub.add_parser("probe", help="HTTP probe API/UI/health")
    probe_p.add_argument(
        "target",
        nargs="?",
        default="all",
        choices=["all", "api", "ui", "health"],
        help="What to probe (default all)",
    )

    tui_p = sub.add_parser("tui", help="Terminal menu UI (not a desktop GUI)")
    tui_p.add_argument(
        "--smoke",
        action="store_true",
        help="Print menu and exit (headless check)",
    )
    tui_p.add_argument(
        "--once",
        metavar="KEY",
        help="Run a single menu key then exit (e.g. v, 2)",
    )

    home_p = sub.add_parser("home", help="Show ROUTISM_HOME / resolved stack root")
    home_p.add_argument(
        "home_cmd",
        nargs="?",
        default="show",
        choices=["show"],
        help="show resolved root",
    )

    return p


def cmd_version(_: argparse.Namespace) -> int:
    print(f"routism-cli {__version__}")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    from pathlib import Path

    dest = Path(args.install_dir).expanduser() if getattr(args, "install_dir", None) else None
    ensure_product_repo(
        dest=dest,
        url=getattr(args, "install_url", None),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    print_json(product_status())
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    as_json = bool(getattr(args, "json", False))
    _require_product(quiet=as_json)
    return run_doctor(as_json=as_json)


def cmd_setup(args: argparse.Namespace) -> int:
    """Ensure product clone, then full stack setup."""
    dry = args.dry_run
    yes = args.yes
    total = 7

    print()
    print(f"  routism-cli setup  v{__version__}" + ("  [dry-run]" if dry else ""))
    print("  ────────────────────────────────────────")
    print("  Standalone CLI: ensure product from GitHub, then")
    print("  Docker + Ollama + engine models + compose up.")
    print(f"  Product: {PRODUCT_REPO_URL}")
    print()

    if not yes and not dry and not confirm("Continue with setup?", default=True):
        info("Cancelled.")
        return 0

    step(1, total, "Ensure product checkout (GitHub)")
    root = _require_product(dry_run=dry)
    ok(f"Product at {root}")

    step(2, total, "Check Docker and Ollama")
    from .docker_ops import check_docker
    from .ollama_ops import check_ollama

    d = check_docker(quiet=False)
    o = check_ollama(quiet=False)

    docker_ok = bool(d.docker_bin and d.compose_argv and d.daemon_ok)
    if not args.skip_docker and not docker_ok:
        if dry:
            warn("Docker not ready (dry-run continues)")
        else:
            print()
            warn("Docker is required to run the API + UI containers.")
            if not d.daemon_ok and d.docker_bin:
                print("  → Start Docker Desktop (or the Docker service), then re-run:  routism")
            else:
                print("  → Install Docker: https://docs.docker.com/get-docker/")
                print("  → Then re-run:  routism")
            if not confirm("Continue setup without Docker? (Ollama/models only)", default=False):
                raise CliError("Docker is not ready. Start Docker and run:  routism")
            args.skip_docker = True

    step(3, total, "Ollama (engine models host)")
    if o.binary and o.reachable:
        ok("Ollama is installed and running")
    else:
        if not yes and not dry:
            if not confirm(
                "Ollama is missing or not running. Set it up now?",
                default=True,
            ):
                raise CliError(
                    "Ollama is required for the Conductor engine.\n"
                    "  Install from https://ollama.com/download then run:  routism"
                )
        ensure_ollama(yes=yes or True, dry_run=dry)

    step(4, total, "Engine models")
    tags = unique_tags(load_engine_tags(root, verbose=True))
    ok(f"Required engine tags: {', '.join(tags)}")

    from .ollama_ops import list_tags, _model_match

    reachable, installed = list_tags()
    missing = [t for t in tags if not _model_match(installed, t)] if reachable else list(tags)

    if not missing:
        ok("All engine models already present — skipping download")
    elif args.skip_pull:
        warn("Skipping model pull (--skip-pull)")
    else:
        if not yes and not dry:
            print()
            info("Engine models can be large (especially qwen2.5:7b).")
            if not confirm(f"Download missing models now? ({', '.join(missing)})", default=True):
                warn("Skipped pulls — Conductor may degrade until models are present")
                args.skip_pull = True
        if not args.skip_pull:
            ensure_models(tags, dry_run=dry, skip_pull=False)

    step(5, total, "Write .env for Docker → host Ollama")
    if not yes and not dry:
        info("Sets OLLAMA_BASE_URL so containers can reach Ollama on your machine.")
        if not confirm("Update .env configuration?", default=True):
            warn("Skipped .env update")
        else:
            ensure_ollama_base_url(root, yes=True, dry_run=dry)
    else:
        ensure_ollama_base_url(root, yes=True, dry_run=dry)

    step(6, total, "Start API + UI (Docker)")
    if args.skip_docker:
        info("Skipping Docker stack")
    else:
        if not yes and not dry:
            if not confirm("Build and start Docker (API :8000 + UI :3000)?", default=True):
                warn("Skipped Docker start — run later:  routism start")
                args.skip_docker = True
        if not args.skip_docker:
            compose_ops.up(root, dry_run=dry, build=True)
            if not dry:
                info("Waiting for API to become healthy…")
                if not compose_ops.wait_for_api(timeout_s=180):
                    raise CliError(
                        "API did not become healthy in time.\n"
                        "  Debug:  routism logs api"
                    )
                compose_ops.smoke_check()
            else:
                info("[dry-run] would wait for API health")

    step(7, total, "Done")
    print()
    ok("Setup complete" + (" (dry-run)" if dry else ""))
    print()
    print(f"  Dashboard   {UI_URL}")
    print("  API         http://localhost:8000")
    print()
    print(agent_env_snippet())
    print()
    info("In the dashboard: Providers → connect models, then API keys → create a key.")
    print()

    if not dry and not args.skip_docker:
        if yes or confirm("Open the dashboard in your browser now?", default=True):
            open_url(UI_URL)

    print()
    info("Later:  routism start | stop | status | doctor | tui")
    return 0


def cmd_start(_: argparse.Namespace) -> int:
    root = _require_product()
    ensure_ollama_base_url(root, yes=True, dry_run=False)
    compose_ops.up(root, dry_run=False, build=True)
    if not compose_ops.wait_for_api(timeout_s=180):
        raise CliError("API did not become healthy. See:  routism logs api")
    compose_ops.smoke_check()
    ok(f"Dashboard {UI_URL}  ·  API http://localhost:8000")
    return 0


def cmd_stop(_: argparse.Namespace) -> int:
    root = _require_product()
    compose_ops.down(root)
    ok("Stack stopped")
    return 0


def cmd_restart(_: argparse.Namespace) -> int:
    root = _require_product()
    compose_ops.restart(root)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    as_json = bool(getattr(args, "json", False))
    root = _require_product(quiet=as_json)
    if as_json:
        return compose_ops.status_json(root)
    return compose_ops.ps(root)


def cmd_logs(args: argparse.Namespace) -> int:
    root = _require_product()
    return compose_ops.logs(root, follow=args.follow, service=args.service)


def cmd_pull_engine(args: argparse.Namespace) -> int:
    from .util import emit_mode

    json_progress = pull_json_enabled(flag=bool(getattr(args, "json", False)))
    root = _require_product(quiet=json_progress)
    if json_progress:
        # Pure NDJSON on stdout: silence human glyphs (ok/info/warn).
        with emit_mode(quiet=True, human_to_stderr=True):
            ensure_ollama(yes=True, dry_run=False, quiet=True)
            tags = unique_tags(load_engine_tags(root, quiet=True, verbose=False))
            ensure_models(tags, dry_run=False, skip_pull=False, json_progress=True)
        return 0
    ensure_ollama(yes=True, dry_run=False, quiet=False)
    tags = unique_tags(load_engine_tags(root, quiet=False, verbose=True))
    ensure_models(tags, dry_run=False, skip_pull=False, json_progress=False)
    return 0


def cmd_open(_: argparse.Namespace) -> int:
    open_url(UI_URL)
    return 0


def cmd_binaries(_: argparse.Namespace) -> int:
    print_json(
        {
            "python3": which("python3"),
            "docker": which("docker"),
            "ollama": which("ollama"),
        }
    )
    return 0


def cmd_env(args: argparse.Namespace) -> int:
    root = _require_product()
    sub = getattr(args, "env_cmd", None) or "show"
    if sub == "show":
        print_json(show_env(root))
        return 0
    if sub == "set":
        k, v = parse_kv(args.assignment)
        set_env_key(root, k, v)
        return 0
    raise CliError(f"Unknown env subcommand: {sub}")


def cmd_support(args: argparse.Namespace) -> int:
    _require_product()
    text = build_support_report()
    print(text)
    if getattr(args, "copy", False):
        import subprocess

        for cmd in (["pbcopy"], ["xclip", "-selection", "clipboard"], ["wl-copy"]):
            try:
                subprocess.run(cmd, input=text.encode("utf-8"), check=True)
                ok(f"Copied via {cmd[0]}")
                break
            except Exception:
                continue
        else:
            warn("No clipboard tool found (pbcopy/xclip/wl-copy)")
    return 0


def cmd_agent_env(_: argparse.Namespace) -> int:
    print(agent_env_snippet())
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    t = getattr(args, "target", "all") or "all"
    if t == "all":
        print_json(probe_all())
    elif t == "api":
        print_json(probe_api())
    elif t == "ui":
        print_json(probe_ui())
    else:
        print_json(probe_health())
    return 0


def cmd_tui(args: argparse.Namespace) -> int:
    from .tui import run_tui

    # smoke / once version do not need product clone
    once = getattr(args, "once", None)
    smoke = bool(getattr(args, "smoke", False))
    if not smoke and once not in (None, "v", "q"):
        _require_product()
    elif not smoke and once is None:
        _require_product()
    return run_tui(once=once, smoke=smoke)


def cmd_home(_: argparse.Namespace) -> int:
    st = product_status()
    try:
        root = find_repo_root()
        st["resolved"] = str(root)
        st["ok"] = True
        print_json(st)
        return 0
    except CliError as e:
        st["resolved"] = None
        st["ok"] = False
        st["error"] = str(e)
        print_json(st)
        return 1


_COMMANDS = {
    "install",
    "setup",
    "doctor",
    "start",
    "stop",
    "restart",
    "status",
    "logs",
    "pull-engine",
    "open",
    "version",
    "binaries",
    "env",
    "support",
    "agent-env",
    "probe",
    "tui",
    "home",
}


def main(argv: Optional[List[str]] = None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)

    if not argv_list or argv_list == ["--help"] or argv_list == ["-h"]:
        if not argv_list:
            argv_list = ["setup"]
    elif argv_list[0] not in _COMMANDS | {"--version", "-h", "--help"} and not argv_list[
        0
    ].startswith("-"):
        pass
    elif argv_list[0] in ("-y", "--yes", "--dry-run", "--skip-pull", "--skip-docker"):
        argv_list = ["setup"] + argv_list

    parser = _build_parser()
    args = parser.parse_args(argv_list)
    if not args.command:
        args = parser.parse_args(["setup"])

    handlers = {
        "install": cmd_install,
        "version": cmd_version,
        "doctor": cmd_doctor,
        "setup": cmd_setup,
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "status": cmd_status,
        "logs": cmd_logs,
        "pull-engine": cmd_pull_engine,
        "open": cmd_open,
        "binaries": cmd_binaries,
        "env": cmd_env,
        "support": cmd_support,
        "agent-env": cmd_agent_env,
        "probe": cmd_probe,
        "tui": cmd_tui,
        "home": cmd_home,
    }
    try:
        return handlers[args.command](args)
    except CliError as e:
        print(f"\nerror: {e}", file=sys.stderr)
        return e.code
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
