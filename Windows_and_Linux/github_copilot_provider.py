"""GitHub Copilot provider backed by the official Copilot SDK."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import webbrowser
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, TypeVar

from aiprovider import AIProvider, TextSetting
from copilot_connection import CopilotConnectionError, list_stored_accounts, read_account_token

if TYPE_CHECKING:
    from copilot import CopilotClient

_Result = TypeVar("_Result")


class _CopilotAuthenticationError(CopilotConnectionError):
    pass


class GitHubCopilotProvider(AIProvider):
    """Use an app-selected GitHub account or the SDK's current account."""

    MODEL_ID = "gpt-5-mini"
    MODEL_NAME = "GPT-5 mini"
    REASONING_EFFORT = "medium"
    SIGN_IN_GUIDE_URL = (
        "https://github.com/github/copilot-sdk/blob/main/docs/auth/authenticate.md"
    )
    REQUEST_TIMEOUT_SECONDS = 120.0
    CONNECTION_TIMEOUT_SECONDS = 30.0
    CLEANUP_TIMEOUT_SECONDS = 10.0
    OPERATION_TIMEOUT_SECONDS = 180.0

    def __init__(self, app: Any) -> None:
        self._active_tasks: set[
            tuple[asyncio.AbstractEventLoop, asyncio.Task]
        ] = set()
        self._active_tasks_lock = threading.Lock()

        super().__init__(
            app,
            "GitHub Copilot",
            [
                TextSetting("github_account", "GitHub account", "",
                            "Blank uses the current Copilot SDK account"),
                TextSetting("model", "Model", self.MODEL_ID, "Copilot model ID"),
                TextSetting("reasoning_effort", "Reasoning effort", self.REASONING_EFFORT,
                            "Blank uses the model default; none requires model support"),
            ],
            "Uses the official GitHub Copilot SDK with your signed-in Copilot CLI account. "
            "No API key or GitHub token is stored by Writing Tools.\n"
            "Selected text and prompts are sent to GitHub Copilot. Requests use that "
            "account's Copilot usage allowance, subject to plan and organization policies.\n"
            "Choose an account stored by GitHub CLI, or use the current SDK account.\n"
            "Sign in once by running `copilot` in a terminal. The SDK runtime downloads "
            "automatically on first use.",
            "",
            "GitHub Copilot Sign-In Guide",
            lambda: webbrowser.open(self.SIGN_IN_GUIDE_URL),
        )

    async def _create_client(self, config: dict) -> CopilotClient:
        try:
            from copilot import CopilotClient
        except ImportError as exc:
            raise CopilotConnectionError(
                "GitHub Copilot support is unavailable because the Copilot SDK "
                "is not installed."
            ) from exc

        if config["github_account"]:
            token = await read_account_token(config["github_account"])
            return CopilotClient(github_token=token, use_logged_in_user=False)
        return CopilotClient(use_logged_in_user=True)

    @staticmethod
    def _snapshot(config: dict) -> dict:
        return {
            "github_account": str(config.get("github_account") or "").strip(),
            "model": str(config.get("model") or GitHubCopilotProvider.MODEL_ID).strip(),
            "reasoning_effort": str(config.get("reasoning_effort", "medium") or "").strip().lower(),
        }

    def _saved_config(self) -> dict:
        return self._snapshot({setting.name: getattr(self, setting.name, setting.default_value)
                               for setting in self.settings})

    @asynccontextmanager
    async def _connected_client(self, config: dict) -> AsyncIterator[CopilotClient]:
        client = await self._create_client(config)
        failed = False
        try:
            await asyncio.wait_for(client.start(), self.CONNECTION_TIMEOUT_SECONDS)
            yield client
        except BaseException:
            failed = True
            raise
        finally:
            try:
                await asyncio.wait_for(client.stop(), self.CLEANUP_TIMEOUT_SECONDS)
            except Exception:
                try:
                    await asyncio.wait_for(client.force_stop(), self.CLEANUP_TIMEOUT_SECONDS)
                except Exception:
                    logging.warning("GitHub Copilot runtime cleanup failed")
                if not failed:
                    raise

    def _run_async(self, operation: Callable[[], Awaitable[_Result]]) -> _Result:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError("GitHub Copilot requests must run outside an asyncio event loop.")

        async def tracked_operation() -> _Result:
            loop = asyncio.get_running_loop()
            task = asyncio.current_task()
            if task is None:
                raise RuntimeError("Could not track the GitHub Copilot request.")

            active_task = (loop, task)
            with self._active_tasks_lock:
                self._active_tasks.add(active_task)
            try:
                async with asyncio.timeout(self.OPERATION_TIMEOUT_SECONDS):
                    return await operation()
            finally:
                with self._active_tasks_lock:
                    self._active_tasks.discard(active_task)

        return asyncio.run(tracked_operation())

    @staticmethod
    def _prepare_request(system_instruction: str, prompt: str | list) -> tuple[str, str]:
        if not isinstance(system_instruction, str):
            raise TypeError("The writing instruction must be text.")

        system_messages = []
        if system_instruction.strip():
            system_messages.append(system_instruction.strip())

        if isinstance(prompt, str):
            request_prompt = prompt
        elif isinstance(prompt, list):
            history = []
            for message in prompt:
                if not isinstance(message, dict):
                    raise TypeError("Conversation messages must be dictionaries.")

                role = message.get("role")
                content = message.get("content")
                if not isinstance(content, str):
                    raise TypeError("Conversation message content must be text.")

                if role == "system":
                    normalized_instruction = content.strip()
                    if normalized_instruction and normalized_instruction not in system_messages:
                        system_messages.append(normalized_instruction)
                elif role in {"user", "assistant"}:
                    history.append({"role": role, "content": content})
                else:
                    raise ValueError(f"Unsupported conversation role: {role!r}")

            if not history:
                raise ValueError("The conversation does not contain any user or assistant messages.")
            request_prompt = (
                "Continue the conversation and respond to the latest user message.\n"
                "Conversation history in JSON:\n"
                + json.dumps(history, ensure_ascii=False)
            )
        else:
            raise TypeError("The writing prompt must be text or a list of messages.")

        if not system_messages:
            raise ValueError("The selected writing option has no system instruction.")
        if not request_prompt.strip():
            raise ValueError("The selected writing option has no prompt.")

        return "\n\n".join(system_messages), request_prompt

    @staticmethod
    def _authentication_message(account: str = "") -> str:
        if account:
            return (
                f"GitHub account {account} could not authenticate with Copilot. "
                "Run `gh auth login --hostname github.com` for that account and "
                "check its Copilot access. "
                f"Sign-in guide: {GitHubCopilotProvider.SIGN_IN_GUIDE_URL}"
            )
        return (
            "Sign in to GitHub Copilot CLI by running `copilot` in a terminal, "
            "then try again. See the sign-in guide: "
            f"{GitHubCopilotProvider.SIGN_IN_GUIDE_URL}"
        )

    @staticmethod
    def _error_message(exc: Exception, config: dict) -> str:
        context = f"Account {config['github_account'] or 'automatic SDK account'}, model {config['model']}: "
        if isinstance(exc, CopilotConnectionError):
            return context + str(exc)
        # Classify, but never display/log SDK exception text: it can contain
        # proxy HTML, request contents, or a credential from a failed transport.
        detail = str(exc).lower()
        if isinstance(exc, TimeoutError) or "timed out" in detail:
            message = "Copilot timed out. Check your connection and try again."
        elif (any(word in detail for word in ("integration", "integrator"))
              and any(word in detail for word in ("model", "unsupported", "not supported"))):
            message = (
                "Copilot rejected this model for the SDK integration. A model can "
                "appear in the catalog but reject requests. Try another listed model "
                "and check Copilot plan, organization policy, and SDK/runtime availability."
            )
        elif any(word in detail for word in ("<html", "<!doctype", "502", "503")):
            message = "Copilot could not reach the service. Check network, proxy, and service availability."
        elif any(word in detail for word in ("401", "403", "unauthorized", "forbidden", "authentication", "credential")):
            message = "Copilot denied access. Check this account's sign-in, Copilot plan, and organization policy."
        elif any(word in detail for word in ("model", "unsupported", "not supported")):
            message = "Copilot rejected the selected model or reasoning effort. Refresh models and choose a supported setting."
        elif any(word in detail for word in ("429", "quota", "rate limit")):
            message = "Copilot usage is currently limited. Check this account's allowance and retry later."
        elif any(word in detail for word in ("network", "connect", "proxy", "dns", "ssl", "certificate")):
            message = "Copilot could not reach the service. Check network, proxy, and service availability."
        else:
            message = "Copilot could not complete the request. Check account access, model availability, network, and SDK setup."
        return context + message

    def _verify_identity(self, auth_status: Any, config: dict) -> str:
        account = config["github_account"]
        if not getattr(auth_status, "isAuthenticated", False):
            raise _CopilotAuthenticationError(self._authentication_message(account))
        login = str(getattr(auth_status, "login", "") or "").strip()
        if account and login.casefold() != account.casefold():
            raise _CopilotAuthenticationError(
                f"The SDK identity ({login or 'unknown'}) does not match selected "
                f"GitHub account {account}. No prompt was sent. Sign in again with GitHub CLI."
            )
        return login

    async def _auth_status(self, client: CopilotClient, config: dict) -> Any:
        auth = await asyncio.wait_for(client.get_auth_status(), self.CONNECTION_TIMEOUT_SECONDS)
        if (config["github_account"] and getattr(auth, "isAuthenticated", False)
                and not getattr(auth, "login", None)):
            # Client status omits login for explicit tokens; session status
            # resolves it. This isolated probe sends no prompt and uses no tools.
            # Never override a nonempty SDK login: mismatches must fail closed.
            async with self._isolated_session(client, "auto", "", {}) as session:
                status = await asyncio.wait_for(
                    session.rpc.git_hub_auth.get_status(), self.CONNECTION_TIMEOUT_SECONDS,
                )
            auth_type = getattr(status, "auth_type", None)
            auth = SimpleNamespace(
                isAuthenticated=status.is_authenticated,
                login=status.login,
                authType=getattr(auth_type, "value", auth_type) or "",
            )
        return auth

    @asynccontextmanager
    async def _isolated_session(self, client: CopilotClient, model: str,
                                instruction: str, reasoning_options: dict) -> AsyncIterator[Any]:
        session = await asyncio.wait_for(client.create_session(
            model=model,
            **reasoning_options,
            available_tools=[],
            enable_config_discovery=False,
            enable_session_telemetry=False,
            enable_file_hooks=False,
            enable_host_git_operations=False,
            enable_session_store=False,
            enable_github_cache_store=False,
            enable_skills=False,
            enable_on_demand_instruction_discovery=False,
            skip_custom_instructions=True,
            system_message={"mode": "replace", "content": instruction},
        ), self.CONNECTION_TIMEOUT_SECONDS)
        failed = False
        try:
            yield session
        except BaseException:
            failed = True
            raise
        finally:
            try:
                await asyncio.wait_for(session.disconnect(), self.CLEANUP_TIMEOUT_SECONDS)
            except Exception:
                if not failed:
                    raise
                logging.warning("GitHub Copilot session cleanup failed")

    def list_accounts(self) -> list[str]:
        """List stored GitHub.com logins; raise a safe error if gh is unavailable."""
        return self._run_async(list_stored_accounts)

    async def _inspect_connection(self, config: dict, result: dict) -> None:
        try:
            async with self._connected_client(config) as client:
                auth = await self._auth_status(client, config)
                result["login"] = str(getattr(auth, "login", "") or "")
                result["auth_type"] = str(getattr(auth, "authType", "") or "")
                self._verify_identity(auth, config)
                result["authenticated"] = True
                models = await asyncio.wait_for(client.list_models(), self.CONNECTION_TIMEOUT_SECONDS)
                result["models"] = [
                    {"id": model.id, "name": getattr(model, "name", None) or model.id,
                     "reasoning_efforts": list(getattr(model, "supported_reasoning_efforts", None) or [])}
                    for model in models
                ]
        except Exception as exc:
            result["error"] = self._error_message(exc, config)

    def inspect_connection(self, config: dict) -> dict:
        """Inspect an unsaved snapshot without sending a model prompt.

        Authentication fields survive catalog/cleanup failures. `authenticated`
        is false on an identity mismatch; `login` still reports the SDK identity.
        """
        snapshot = self._snapshot(config)
        result = {"authenticated": False, "login": "", "auth_type": "", "models": []}
        try:
            self._run_async(lambda: self._inspect_connection(snapshot, result))
        except asyncio.CancelledError:
            result["error"] = "GitHub Copilot connection inspection was cancelled."
        except Exception as exc:
            result["error"] = self._error_message(exc, snapshot)
        return result

    async def _send_request(self, system_instruction: str, prompt: str, config: dict,
                            identity: dict) -> str | None:
        async with self._connected_client(config) as client:
            auth_status = await self._auth_status(client, config)
            identity["login"] = self._verify_identity(auth_status, config)
            # Discovery can be blocked or omit working models. Only inspection
            # lists models; inference validates the selected model and effort.
            effort = config["reasoning_effort"]
            reasoning_options = {"reasoning_effort": effort} if effort else {}
            async with self._isolated_session(
                client, config["model"], system_instruction, reasoning_options,
            ) as session:
                response = await asyncio.wait_for(session.send_and_wait(
                    prompt, timeout=self.REQUEST_TIMEOUT_SECONDS,
                ), self.REQUEST_TIMEOUT_SECONDS)

        if response is None:
            return None
        content = getattr(getattr(response, "data", None), "content", None)
        return content if isinstance(content, str) else None

    def get_response(
        self,
        system_instruction: str,
        prompt: str | list,
        return_response: bool = False,
    ) -> str:
        snapshot = self._saved_config()
        identity: dict[str, str] = {}
        try:
            prepared_instruction, prepared_prompt = self._prepare_request(
                system_instruction,
                prompt,
            )
            response_text = self._run_async(
                lambda: self._send_request(prepared_instruction, prepared_prompt, snapshot, identity)
            )
        except asyncio.CancelledError:
            logging.info("GitHub Copilot request cancelled")
            return ""
        except _CopilotAuthenticationError as exc:
            logging.warning("GitHub Copilot sign-in is required")
            self.app.show_message_signal.emit(
                "GitHub Copilot sign-in required",
                self._error_message(exc, snapshot),
            )
            return ""
        except Exception as exc:
            logging.error("GitHub Copilot request failed")
            self.app.show_message_signal.emit(
                "GitHub Copilot error",
                self._error_message(exc, {**snapshot, "github_account": snapshot["github_account"] or identity.get("login", "")}),
            )
            return ""

        if not isinstance(response_text, str) or not response_text.strip():
            logging.error("GitHub Copilot returned an empty response")
            self.app.show_message_signal.emit(
                "GitHub Copilot error",
                "GitHub Copilot returned no text. Please try the request again.",
            )
            return ""

        response_text = response_text.strip()
        if not return_response:
            self.app.output_ready_signal.emit(response_text)
        return response_text

    def validate_connection(self, config: dict) -> tuple[bool, str]:
        """Send one synthetic request using an unsaved account/model snapshot."""
        snapshot = self._snapshot(config)
        identity: dict[str, str] = {}
        try:
            response = self._run_async(lambda: self._send_request(
                "This is a connection test. Reply with OK only.", "Reply OK.", snapshot, identity,
            ))
            if not isinstance(response, str) or not response.strip():
                raise CopilotConnectionError("Copilot returned no text for the connection test.")
        except asyncio.CancelledError:
            return False, "GitHub Copilot connection test was cancelled."
        except Exception as exc:
            # For automatic mode include the identity actually verified, when known.
            context = dict(snapshot)
            context["github_account"] = snapshot["github_account"] or identity.get("login", "")
            return False, self._error_message(exc, context)
        return True, (
            f"GitHub account {identity.get('login') or snapshot['github_account'] or 'automatic SDK account'}, "
            f"model {snapshot['model']}: connection test succeeded with a synthetic prompt."
        )

    def after_load(self) -> None:
        pass

    def before_load(self) -> None:
        self.cancel()

    def cancel(self) -> None:
        with self._active_tasks_lock:
            active_tasks = tuple(self._active_tasks)

        for loop, task in active_tasks:
            if loop.is_closed():
                continue
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                logging.debug("GitHub Copilot request already completed during cancellation")
