"""HTTP probes for API / UI / health endpoints."""

from __future__ import annotations

from typing import Any, Dict

from .util import API_BASE, API_HEALTH_URL, API_MODELS_URL, UI_URL, http_get


def probe_url(url: str, *, timeout: float = 3.0) -> Dict[str, Any]:
    code, body = http_get(url, timeout=timeout)
    ok = code == 200 or (url.rstrip("/").endswith("3000") and 200 <= code < 500)
    return {
        "url": url,
        "http_status": code,
        "ok": bool(ok and code),
        "body_preview": (body or "")[:200],
    }


def probe_api() -> Dict[str, Any]:
    return probe_url(API_MODELS_URL)


def probe_ui() -> Dict[str, Any]:
    return probe_url(UI_URL)


def probe_health() -> Dict[str, Any]:
    return probe_url(API_HEALTH_URL)


def probe_all() -> Dict[str, Any]:
    return {
        "api": probe_api(),
        "ui": probe_ui(),
        "health": probe_health(),
        "api_base": API_BASE,
    }
