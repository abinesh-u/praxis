"""praxis version — display version and environment information."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

from praxis_cli.render import console


def version_cmd() -> None:
    """Print version and platform runtime environment."""
    try:
        ver = version("praxis-cli")
    except PackageNotFoundError:
        ver = "0.1.0"

    console.print(f"praxis {ver} (Python {sys.version.split()[0]} on {sys.platform})")
