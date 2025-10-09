"""Shared helpers for colored environment tags in CLI/log output."""
from __future__ import annotations

import click

_ENV_COLOR_MAP = {
    "int": "cyan",
    "stg": "green",
    "preview": "yellow",
    "prod": "red",
}

__all__ = ["format_env_tag", "log_env", "log_info", "log_warn", "log_error"]


def format_env_tag(env: str) -> str:
    normalized = (env or "").strip().lower()
    tag = f"[{(env or '').strip().upper()}]"
    color = _ENV_COLOR_MAP.get(normalized)
    if color:
        return click.style(tag, fg=color)
    return tag


def log_env(env: str, message: str, *, level: str = "info", err: bool = False) -> None:
    tag = format_env_tag(env)
    level_normalized = (level or "info").lower()
    stream_err = err or level_normalized in {"warn", "warning", "error"}
    click.echo(f"{tag} {message}", err=stream_err)


def log_info(env: str, message: str) -> None:
    log_env(env, message, level="info")


def log_warn(env: str, message: str) -> None:
    log_env(env, message, level="warn", err=True)


def log_error(env: str, message: str) -> None:
    log_env(env, message, level="error", err=True)
