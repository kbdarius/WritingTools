import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from copilot_connection import (
    CopilotConnectionError,
    _run_gh,
    list_stored_accounts,
    read_account_token,
    stored_account_environment,
)


class CopilotConnectionTests(unittest.IsolatedAsyncioTestCase):
    def test_environment_removes_all_token_overrides_and_debug_without_mutation(self) -> None:
        environment = {
            "GH_TOKEN": "secret", "GITHUB_TOKEN": "secret", "GH_ENTERPRISE_TOKEN": "secret",
            "GITHUB_ENTERPRISE_TOKEN": "secret", "COPILOT_GITHUB_TOKEN": "secret", "GH_DEBUG": "api",
            "gh_token": "secret", "PATH": "bin", "GH_CONFIG_DIR": "stored-accounts",
        }
        with patch.dict(os.environ, environment, clear=True):
            original = dict(os.environ)
            scrubbed = stored_account_environment()
            self.assertEqual(dict(os.environ), original)
        self.assertEqual(scrubbed, {"PATH": "bin", "GH_CONFIG_DIR": "stored-accounts", "GH_PROMPT_DISABLED": "1"})

    async def test_account_list_includes_inactive_and_expired_accounts(self) -> None:
        result = {"hosts": {"github.com": [
            {"login": "bob", "active": True}, {"login": "alice", "active": False, "state": "failure"},
            {"login": "bob", "active": True},
        ], "enterprise.example": [{"login": "unrelated"}]}}
        with patch("copilot_connection._run_gh", new_callable=AsyncMock,
                   return_value=json.dumps(result)) as run:
            self.assertEqual(await list_stored_accounts(), ["alice", "bob"])
        run.assert_awaited_once_with("auth", "status", "--hostname", "github.com", "--json", "hosts")

    async def test_empty_account_list(self) -> None:
        with patch("copilot_connection._run_gh", new_callable=AsyncMock, return_value='{"hosts": {}}'):
            self.assertEqual(await list_stored_accounts(), [])

    async def test_bad_account_output_is_not_echoed(self) -> None:
        with patch("copilot_connection._run_gh", new_callable=AsyncMock, return_value="secret"):
            with self.assertRaises(CopilotConnectionError) as raised:
                await list_stored_accounts()
        self.assertNotIn("secret", str(raised.exception))

    async def test_token_command_names_exact_account_and_never_switches(self) -> None:
        with patch("copilot_connection._run_gh", new_callable=AsyncMock, return_value="in-memory-token") as run:
            self.assertEqual(await read_account_token("alice"), "in-memory-token")
        run.assert_awaited_once_with("auth", "token", "--hostname", "github.com", "--user", "alice")

    async def test_invalid_login_is_rejected_before_subprocess(self) -> None:
        with patch("copilot_connection._run_gh", new_callable=AsyncMock) as run:
            for login in ("", "--user", "alice; command", "alice\n", "a" * 40):
                with self.subTest(login=login), self.assertRaises(CopilotConnectionError):
                    await read_account_token(login)
        run.assert_not_awaited()

    async def test_empty_or_malformed_token_is_not_echoed(self) -> None:
        for token in ("", "secret\nextra"):
            with patch("copilot_connection._run_gh", new_callable=AsyncMock, return_value=token):
                with self.assertRaises(CopilotConnectionError) as raised:
                    await read_account_token("alice")
                self.assertNotIn("secret", str(raised.exception))

    async def test_subprocess_uses_scrubbed_environment_and_captured_stdout_only(self) -> None:
        process = Mock(returncode=0)
        process.communicate = AsyncMock(return_value=(b"secret\n", None))
        with (
            patch.dict(os.environ, {"GH_TOKEN": "override", "GH_DEBUG": "api"}),
            patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=process) as spawn,
        ):
            self.assertEqual(await _run_gh("auth", "token"), "secret")
        self.assertEqual(spawn.await_args.args, ("gh", "auth", "token"))
        options = spawn.await_args.kwargs
        self.assertNotIn("GH_TOKEN", options["env"])
        self.assertNotIn("GH_DEBUG", options["env"])
        self.assertEqual(options["stderr"], asyncio.subprocess.DEVNULL)
        self.assertEqual(options["stdin"], asyncio.subprocess.DEVNULL)
        self.assertNotIn("shell", options)

    async def test_missing_gh_has_actionable_error(self) -> None:
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("secret")):
            with self.assertRaisesRegex(CopilotConnectionError, "Install it") as raised:
                await _run_gh("auth", "status")
        self.assertNotIn("secret", str(raised.exception))

    async def test_failed_gh_never_exposes_stdout(self) -> None:
        process = Mock(returncode=1)
        process.communicate = AsyncMock(return_value=(b"secret", None))
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=process):
            with self.assertRaises(CopilotConnectionError) as raised:
                await _run_gh("auth", "token")
        self.assertNotIn("secret", str(raised.exception))

    async def test_timeout_and_cancellation_kill_and_reap_gh(self) -> None:
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                started = asyncio.Event()

                async def hang() -> None:
                    started.set()
                    await asyncio.Event().wait()

                process = Mock(returncode=None)
                process.communicate = hang
                process.wait = AsyncMock(return_value=0)
                with (
                    patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=process),
                    patch("copilot_connection.GH_TIMEOUT_SECONDS", 0.02 if not cancel else 10),
                ):
                    task = asyncio.create_task(_run_gh("auth", "token"))
                    await started.wait()
                    if cancel:
                        task.cancel()
                    with self.assertRaises(asyncio.CancelledError if cancel else CopilotConnectionError):
                        await task
                process.kill.assert_called_once()
                process.wait.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
