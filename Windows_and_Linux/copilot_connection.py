"""Read GitHub CLI credentials without changing its active account."""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess

GH_TIMEOUT_SECONDS = 15.0
TOKEN_ENVIRONMENT_VARIABLES = {
    "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN",
    "COPILOT_GITHUB_TOKEN", "GH_DEBUG",
}


class CopilotConnectionError(RuntimeError):
    """An application-owned message safe to display without credentials."""


def stored_account_environment() -> dict[str, str]:
    """Preserve CLI configuration paths, but never override stored credentials."""
    environment = {
        key: value for key, value in os.environ.items()
        if key.upper() not in TOKEN_ENVIRONMENT_VARIABLES
    }
    environment["GH_PROMPT_DISABLED"] = "1"
    return environment


async def _run_gh(*arguments: str) -> str:
    process = None
    try:
        async with asyncio.timeout(GH_TIMEOUT_SECONDS):
            process = await asyncio.create_subprocess_exec(
                "gh", *arguments,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=stored_account_environment(),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            stdout, _ = await process.communicate()
            if process.returncode:
                raise CopilotConnectionError(
                    "GitHub CLI could not read the stored account. Run `gh auth login "
                    "--hostname github.com` for that account and try again."
                )
            return stdout.decode("utf-8").strip()
    except FileNotFoundError:
        raise CopilotConnectionError(
            "GitHub CLI (gh) was not found. Install it and run "
            "`gh auth login --hostname github.com` to select a stored account."
        ) from None
    except TimeoutError:
        raise CopilotConnectionError("GitHub CLI account lookup timed out. Try again.") from None
    except (OSError, UnicodeError):
        raise CopilotConnectionError("GitHub CLI account lookup failed. Check its installation.") from None
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await asyncio.wait_for(process.wait(), timeout=5.0)


async def list_stored_accounts() -> list[str]:
    # Never use --show-token, --active, or auth switch. Invalid/expired stored
    # accounts remain selectable so the UI can explain their authentication error.
    output = await _run_gh("auth", "status", "--hostname", "github.com", "--json", "hosts")
    try:
        accounts = json.loads(output)["hosts"].get("github.com", [])
        return sorted({entry["login"] for entry in accounts if entry.get("login")}, key=str.casefold)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise CopilotConnectionError("GitHub CLI returned an unreadable account list.") from None


async def read_account_token(login: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", login):
        raise CopilotConnectionError("Choose a valid GitHub.com account login.")
    token = await _run_gh("auth", "token", "--hostname", "github.com", "--user", login)
    if not token or any(character.isspace() for character in token):
        raise CopilotConnectionError("GitHub CLI returned no usable token for the selected account.")
    return token
