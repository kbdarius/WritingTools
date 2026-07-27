"""Read-only Azure Speech usage checks through the locally installed Azure CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any


AZURE_CLI_INSTALL_URL = "https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows"
AZURE_POWERSHELL_INSTALL_URL = "https://learn.microsoft.com/en-us/powershell/azure/install-azure-powershell"
F0_MONTHLY_CHARACTERS = 500_000


def azure_cli_path() -> str | None:
    found = shutil.which("az")
    if found:
        return found
    if os.name == "nt":
        for candidate in (
            os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft SDKs", "Azure", "CLI2", "wbin", "az.cmd"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft SDKs", "Azure", "CLI2", "wbin", "az.cmd"),
        ):
            if candidate and os.path.exists(candidate):
                return candidate
    return None


def azure_powershell_available() -> bool:
    command = shutil.which("powershell") or shutil.which("pwsh")
    if not command:
        return False
    try:
        result = subprocess.run(
            [command, "-NoProfile", "-NonInteractive", "-Command",
             "if (Get-Module -ListAvailable -Name Az.Accounts) { exit 0 } else { exit 1 }"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _run_cli(cli: str, *arguments: str) -> Any:
    result = subprocess.run(
        [cli, *arguments], capture_output=True, text=True, timeout=45,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or "Azure CLI command failed.")
    try:
        return json.loads(result.stdout or "null")
    except json.JSONDecodeError as exc:
        raise RuntimeError("Azure CLI returned an invalid response.") from exc


def _next_month_reset(now: datetime) -> str:
    year, month = now.year, now.month
    if month == 12:
        year, month = year + 1, 1
    else:
        month += 1
    return f"{year:04d}-{month:02d}-01"


def get_speech_usage(config: dict) -> dict[str, Any]:
    """Return current-month Speech usage and F0 quota information."""
    cli = azure_cli_path()
    if not cli:
        raise RuntimeError("Azure CLI is not installed on this PC.")
    if not _run_cli(cli, "account", "show", "--output", "json"):
        raise RuntimeError("Azure CLI is not signed in. Run 'az login' first.")

    configured_resource_id = (config.get("azure_speech", {}).get("resource_id", "") or "").strip()
    if configured_resource_id:
        resources = [{"id": configured_resource_id, "name": configured_resource_id.rsplit("/", 1)[-1]}]
    else:
        resources = _run_cli(
            cli, "resource", "list", "--resource-type", "Microsoft.CognitiveServices/accounts",
            "--query", "[?kind=='SpeechServices'].{id:id,name:name}", "--output", "json",
        ) or []
    if not resources:
        raise RuntimeError("No Azure Speech resource was found in the signed-in subscription.")
    if len(resources) > 1:
        raise RuntimeError("Multiple Azure Speech resources were found. Add the Speech resource ID in Settings.")

    resource = resources[0]
    resource_id = resource["id"]
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    metric = _run_cli(
        cli, "monitor", "metrics", "list", "--resource", resource_id,
        "--metric", "SynthesizedCharacters", "--aggregation", "Total", "--interval", "PT1H",
        "--start-time", start.isoformat().replace("+00:00", "Z"),
        "--end-time", now.isoformat().replace("+00:00", "Z"), "--output", "json",
    )
    points = []
    for series in (metric.get("value", [{}])[0].get("timeseries", []) or []):
        points.extend(series.get("data", []) or [])
    characters = int(sum(float(point.get("total", 0) or 0) for point in points))
    sku = _run_cli(cli, "resource", "show", "--ids", resource_id, "--query", "sku.name", "--output", "json")
    quota = F0_MONTHLY_CHARACTERS if str(sku).upper() == "F0" else None
    remaining = max(0, quota - characters) if quota is not None else None
    percent_used = (characters / quota * 100) if quota else None
    return {
        "resource_name": resource.get("name", "Speech resource"), "sku": str(sku),
        "characters": characters, "quota": quota, "remaining": remaining,
        "percent_used": percent_used,
        "percent_remaining": (100 - percent_used) if percent_used is not None else None,
        "reset_date": _next_month_reset(now.astimezone()),
        "checked_at": now.astimezone().strftime("%Y-%m-%d %H:%M %Z"),
    }
