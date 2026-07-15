"""Tests for standalone routism-cli (not the product monorepo)."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from routism_cli import main as cli_main
from routism_cli.env_ops import set_env_key, show_env
from routism_cli.product import ensure_product_repo, is_product_root, product_status
from routism_cli.support import redact_secrets
from routism_cli.util import CliError


def _fake_product(td: Path) -> Path:
    (td / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    orch = td / "routism_orch"
    orch.mkdir()
    (orch / "orch.yaml").write_text("models: []\n", encoding="utf-8")
    return td


class TestProduct(unittest.TestCase):
    def test_is_product_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            self.assertFalse(is_product_root(p))
            _fake_product(p)
            self.assertTrue(is_product_root(p))

    def test_ensure_existing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = _fake_product(Path(td))
            with mock.patch.dict(os.environ, {"ROUTISM_HOME": str(p)}, clear=False):
                got = ensure_product_repo(dest=p)
                self.assertEqual(got, p.resolve())
                self.assertEqual(os.environ.get("ROUTISM_HOME"), str(p.resolve()))


class TestEntry(unittest.TestCase):
    def test_version(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli_main.main(["version"])
        self.assertEqual(code, 0)
        self.assertIn("routism-cli", out.getvalue())

    def test_help(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                cli_main.main(["--help"])
        self.assertEqual(cm.exception.code, 0)

    def test_tui_smoke(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli_main.main(["tui", "--smoke"])
        self.assertEqual(code, 0)
        self.assertIn("Routism TUI", out.getvalue())
        self.assertIn("Env set", out.getvalue())

    def test_install_dry_run(self) -> None:
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "Routism"
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = cli_main.main(
                    ["install", "--dir", str(dest), "--dry-run"]
                )
        self.assertEqual(code, 0)
        self.assertIn("product_git", out.getvalue())

    def test_env_set_backslash(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _fake_product(Path(td))
            set_env_key(root, "MANAGEMENT_API_KEY", r"x\1y")
            self.assertEqual(show_env(root)["MANAGEMENT_API_KEY"], r"x\1y")

    def test_redact(self) -> None:
        s = redact_secrets("rtm_abcdefghijklmnopqrstuvwx and José")
        self.assertIn("rtm_***", s)
        self.assertNotIn("rtm_abcdefghijklmnopqrstuvwx", s)

    def test_binaries(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli_main.main(["binaries"])
        self.assertEqual(code, 0)
        json.loads(out.getvalue())

    def test_doctor_json_with_fake_home(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _fake_product(Path(td))
            out = io.StringIO()
            err = io.StringIO()
            with mock.patch.dict(os.environ, {"ROUTISM_HOME": str(root)}):
                with redirect_stdout(out), redirect_stderr(err):
                    code = cli_main.main(["doctor", "--json"])
            self.assertIn(code, (0, 1))
            body = out.getvalue()
            self.assertNotIn("✓", body)
            self.assertNotIn("Product stack", body)
            data = json.loads(body)
            self.assertIn("ok", data)


if __name__ == "__main__":
    unittest.main()
