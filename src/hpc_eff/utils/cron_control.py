"""Utilities to enable/disable a cron job at /etc/cron.d/hpc-eff.

This module provides two simple functions:
- `enable_cron(cron_path, command, interval_minutes)` – write a cron file
  that runs `command` every `interval_minutes` minutes as root.
- `disable_cron(cron_path)` – remove the cron file if it exists.

Note: writing to `/etc/cron.d` requires root privileges. Caller should
check permissions and handle errors appropriately.
"""
from __future__ import annotations

import os
import tempfile
from typing import Optional


DEFAULT_CRON_PATH = "/etc/cron.d/hpc-eff"


def enable_cron(cron_path: str = DEFAULT_CRON_PATH,
                command: str = "/usr/bin/hpc-eff",
                interval_minutes: int = 10) -> None:
    """Create or overwrite a cron file that runs `command` every
    `interval_minutes` minutes as root.

    This writes an atomic file and sets permissions to 0644.
    Raises PermissionError if not running as root.
    """
    if os.geteuid() != 0:
        raise PermissionError("enabling cron requires root privileges")

    if interval_minutes <= 0 or interval_minutes > 60:
        raise ValueError("interval_minutes must be between 1 and 60")

    # Cron time specification (*/N * * * *) for every N minutes
    schedule = f"*/{interval_minutes} * * * *"

    content_lines = [
        "# /etc/cron.d/hpc-eff - managed by hpc-eff",
        "SHELL=/bin/sh",
        "PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin",
        f"{schedule} root {command} >/dev/null 2>&1",
    ]
    content = "\n".join(content_lines) + "\n"

    # write atomically to avoid partial files
    dir_name = os.path.dirname(cron_path)
    fd, tmp_path = tempfile.mkstemp(prefix="hpc-eff-cron-", dir=dir_name)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.chmod(tmp_path, 0o644)
        # atomic replace
        os.replace(tmp_path, cron_path)
    finally:
        # if something went wrong and tmp still exists, remove it
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def disable_cron(cron_path: str = DEFAULT_CRON_PATH) -> None:
    """Remove cron file if it exists. Requires root privileges."""
    if os.geteuid() != 0:
        raise PermissionError("disabling cron requires root privileges")

    try:
        if os.path.exists(cron_path):
            os.remove(cron_path)
    except FileNotFoundError:
        pass
