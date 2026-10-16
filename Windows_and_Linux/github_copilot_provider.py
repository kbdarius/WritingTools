"""GitHub Copilot provider backed by the official Copilot SDK."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import webbrowser
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

from aiprovider import AIProvider

if TYPE_CHECKING:
    from copilot import CopilotClient

_Result = TypeVar("_Result")


class _CopilotAuthenticationError(RuntimeError):
    pass


class GitHubCopilotProvider(AIProvider):
    """Use the current user's signed-in Copilot CLI account."""

    MODEL_ID = "gpt-5-mini"
    MODEL_NAME = "GPT-5 mini"
    REASONING_EFFORT = "medium"
    SIGN_IN_GUIDE_URL = (
        "https://github.com/github/copilot-sdk/blob/main/docs/auth/authenticate.md"
    )
    REQUEST_TIMEOUT_SECONDS = 120.0

    def __init__(self, app):
        self._active_tasks: set[
            tuple[asyncio.AbstractEventLoop, asyncio.Task]
        ] = set()
        self._active_tasks_lock = threading.Lock()

        super().__init__(
            app,
            "GitHub Copilot",
            [],
            "Uses the official GitHub Copilot SDK with your signed-in Copilot CLI account. "
            "No API key or GitHub token is stored by Writing Tools.\n"
            "Selected text and prompts are sent to GitHub Copilot. Requests use that "
            "account's Copilot usage allowance, subject to plan and organization policies.\n"
            "Writing actions use GPT-5 mini with medium reasoning effort.\n"
            "Sign in once by running `copilot` in a terminal. The SDK runtime downloads "
            "automatically on first use.",
            "",
            "GitHub Copilot Sign-In Guide",
            lambda: webbrowser.open(self.SIGN_IN_GUIDE_URL),
        )

    def _create_client(self) -> CopilotClient:
        try:
            from copilot import CopilotClient
        except ImportError as exc:
            raise RuntimeError(
                "GitHub Copilot support is unavailable because the Copilot SDK "
                "is not installed."
            ) from exc

        return CopilotClient(use_logged_in_user=True)

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
    def _authentication_message(auth_status: Any) -> str:
        detail = str(getattr(auth_status, "statusMessage", "") or "").strip()
        instructions = (
            "Sign in to GitHub Copilot CLI by running `copilot` in a terminal, "
            "then try again. See the sign-in guide: "
            f"{GitHubCopilotProvider.SIGN_IN_GUIDE_URL}"
        )
        return f"{detail}\n\n{instructions}" if detail else instructions

    async def _get_connection_status(self):
        async with self._create_client() as client:
            auth_status = await client.get_auth_status()
            if not getattr(auth_status, "isAuthenticated", False):
                return auth_status, []
            return auth_status, await client.list_models()

    async def _send_request(self, system_instruction: str, prompt: str) -> str | None:
        async with self._create_client() as client:
            auth_status = await client.get_auth_status()
            if not getattr(auth_status, "isAuthenticated", False):
                raise _CopilotAuthenticationError(
                    self._authentication_message(auth_status)
                )

            async with await client.create_session(
                model=self.MODEL_ID,
                reasoning_effort=self.REASONING_EFFORT,
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
                system_message={
                    "mode": "replace",
                    "content": system_instruction,
                },
            ) as session:
                response = await session.send_and_wait(
                    prompt,
                    timeout=self.REQUEST_TIMEOUT_SECONDS,
                )

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
        try:
            prepared_instruction, prepared_prompt = self._prepare_request(
                system_instruction,
                prompt,
            )
            response_text = self._run_async(
                lambda: self._send_request(prepared_instruction, prepared_prompt)
            )
        except asyncio.CancelledError:
            logging.info("GitHub Copilot request cancelled")
            return ""
        except _CopilotAuthenticationError as exc:
            logging.warning("GitHub Copilot sign-in is required")
            self.app.show_message_signal.emit(
                "GitHub Copilot sign-in required",
                str(exc),
            )
            return ""
        except Exception as exc:
            logging.error("Error processing GitHub Copilot response: %s", exc, exc_info=True)
            self.app.show_message_signal.emit(
                "GitHub Copilot error",
                "GitHub Copilot could not complete the request. Check your sign-in, "
                "plan allowance, and network connection, then try again.\n\n"
                f"Details: {exc}",
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

    def validate_connection(self, _config: dict):
        try:
            auth_status, models = self._run_async(self._get_connection_status)
        except asyncio.CancelledError:
            return False, "GitHub Copilot sign-in check was cancelled."
        except Exception as exc:
            logging.error("Could not verify GitHub Copilot sign-in: %s", exc, exc_info=True)
            return False, (
                "Could not start the GitHub Copilot runtime or check sign-in. "
                "Verify internet access and Copilot CLI setup. "
                f"Details: {exc}"
            )

        if not getattr(auth_status, "isAuthenticated", False):
            return False, self._authentication_message(auth_status)

        model = next(
            (candidate for candidate in models if getattr(candidate, "id", None) == self.MODEL_ID),
            None,
        )
        if model is None:
            return False, (
                f"{self.MODEL_NAME} is not currently listed for this signed-in Copilot CLI "
                "account. Check model rollout, plan availability, and organization policy."
            )

        supported_efforts = getattr(model, "supported_reasoning_efforts", None)
        if supported_efforts is not None and self.REASONING_EFFORT not in supported_efforts:
            return False, (
                f"{self.MODEL_NAME} is available, but medium reasoning effort is not "
                "listed as supported for this account."
            )

        return True, (
            f"GitHub Copilot CLI sign-in detected. {self.MODEL_NAME} with medium reasoning "
            "effort is available. This check sent no model request."
        )

    def after_load(self):
        pass

    def before_load(self):
        self.cancel()

    def cancel(self):
        with self._active_tasks_lock:
            active_tasks = tuple(self._active_tasks)

        for loop, task in active_tasks:
            if loop.is_closed():
                continue
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                logging.debug("GitHub Copilot request already completed during cancellation")
