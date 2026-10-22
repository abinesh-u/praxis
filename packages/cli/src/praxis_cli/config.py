"""Configuration, profile identity, and path management for Praxis CLI."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PROFILE_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
DEFAULT_PRAXIS_DIR = Path.home() / ".praxis"


class ConfigError(Exception):
    """Base error for configuration issues."""


class InvalidProfileError(ConfigError):
    """Raised when a profile name does not match validation criteria."""


class ProfileNotFoundError(ConfigError):
    """Raised when an explicit profile does not exist."""


@dataclass(frozen=True)
class CliConfig:
    """Resolved runtime configuration for CLI invocation."""

    profile: str
    store_path: Path
    timezone: str
    praxis_dir: Path


def validate_profile_name(name: str) -> str:
    """Ensure profile name is safe against path traversal and special characters."""
    clean = name.strip()
    if not clean or not PROFILE_NAME_REGEX.match(clean):
        msg = f"Invalid profile name '{name}'. Must be 1-64 alphanumeric, hyphens, or underscores."
        raise InvalidProfileError(msg)
    return clean


def resolve_timezone(tz_override: str | None = None) -> str:
    """Resolve active timezone string, validating against IANA database."""
    candidate = tz_override or os.getenv("PRAXIS_TIMEZONE")
    if not candidate:
        # Try local system timezone
        try:
            return str(datetime_zone())
        except Exception:
            return "UTC"

    try:
        ZoneInfo(candidate)
        return candidate
    except ZoneInfoNotFoundError as err:
        msg = f"Invalid timezone '{candidate}'. Must be a valid IANA timezone."
        raise ConfigError(msg) from err


def datetime_zone() -> ZoneInfo:
    """Retrieve system local timezone."""
    import time

    tz_name = time.tzname[0]
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def resolve_config(
    profile_override: str | None = None,
    tz_override: str | None = None,
    store_path_override: Path | None = None,
) -> CliConfig:
    """Resolve identity and storage paths with strict fail-closed precedence.

    Precedence:
    1. CLI argument (--profile)
    2. PRAXIS_PROFILE environment variable
    3. Workspace configuration (.praxis/config.json in cwd or parents)
    4. Global configuration (~/.praxis/config.json)
    5. Default profile ("default")
    """
    praxis_dir = DEFAULT_PRAXIS_DIR
    custom_dir = os.getenv("PRAXIS_HOME")
    if custom_dir:
        praxis_dir = Path(custom_dir)

    # Custom store path override (primarily for tests)
    if store_path_override:
        profile = profile_override or "test"
        validate_profile_name(profile)
        tz = resolve_timezone(tz_override)
        return CliConfig(
            profile=profile,
            store_path=store_path_override,
            timezone=tz,
            praxis_dir=praxis_dir,
        )

    env_store = os.getenv("PRAXIS_STORE_PATH")
    if env_store:
        profile = profile_override or "custom"
        validate_profile_name(profile)
        tz = resolve_timezone(tz_override)
        return CliConfig(
            profile=profile,
            store_path=Path(env_store),
            timezone=tz,
            praxis_dir=praxis_dir,
        )

    # 1. CLI option
    if profile_override is not None:
        profile = validate_profile_name(profile_override)
    # 2. Environment variable
    elif os.getenv("PRAXIS_PROFILE"):
        profile = validate_profile_name(os.environ["PRAXIS_PROFILE"])
    # 3. Workspace config
    else:
        workspace_profile = _find_workspace_profile()
        if workspace_profile:
            profile = validate_profile_name(workspace_profile)
        else:
            # 4. Global config
            global_profile = _find_global_profile(praxis_dir)
            profile = validate_profile_name(global_profile) if global_profile else "default"

    store_path = praxis_dir / "profiles" / profile / "store.json"
    tz = resolve_timezone(tz_override)

    return CliConfig(
        profile=profile,
        store_path=store_path,
        timezone=tz,
        praxis_dir=praxis_dir,
    )


def _find_workspace_profile() -> str | None:
    current = Path.cwd()
    for parent in [current, *current.parents]:
        ws_config = parent / ".praxis" / "config.json"
        if ws_config.exists():
            try:
                data = json.loads(ws_config.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "profile" in data:
                    return str(data["profile"])
            except Exception as e:
                raise ConfigError(f"Malformed workspace config at {ws_config}: {e}") from e
    return None


def _find_global_profile(praxis_dir: Path) -> str | None:
    global_config = praxis_dir / "config.json"
    if global_config.exists():
        try:
            data = json.loads(global_config.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "active_profile" in data:
                return str(data["active_profile"])
        except Exception as e:
            raise ConfigError(f"Malformed global config at {global_config}: {e}") from e
    return None
