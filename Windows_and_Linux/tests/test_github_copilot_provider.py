import asyncio
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from github_copilot_provider import GitHubCopilotProvider


class FakeSignal:
    def __init__(self):
        self.emitted = []

    def emit(self, *args):
        self.emitted.append(args)


class FakeApp:
    def __init__(self):
        self.output_ready_signal = FakeSignal()
        self.show_message_signal = FakeSignal()


class FakeSession:
    def __init__(self, response_text="Copilot response", started=None, wait=False):
        self.response_text = response_text
        self.started = started
        self.wait = wait
        self.prompt = None
        self.timeout = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def disconnect(self):
        pass

    async def send_and_wait(self, prompt, *, timeout):
        self.prompt = prompt
        self.timeout = timeout
        if self.started:
            self.started.set()
        if self.wait:
            await asyncio.Event().wait()
        return SimpleNamespace(data=SimpleNamespace(content=self.response_text))


class FakeClient:
    def __init__(
        self,
        authenticated=True,
        response_text="Copilot response",
        started=None,
        wait=False,
        models=None,
        login="alice",
        auth_type="token",
        catalog_error=None,
        request_error=None,
        session_login=None,
    ):
        self.catalog_error = catalog_error
        self.request_error = request_error
        self.stopped = False
        self.auth_status = SimpleNamespace(
            login=login,
            authType=auth_type,
            isAuthenticated=authenticated,
            statusMessage="Not signed in" if not authenticated else "",
        )
        self.models = models if models is not None else [
            SimpleNamespace(
                id=GitHubCopilotProvider.MODEL_ID,
                supported_reasoning_efforts=[GitHubCopilotProvider.REASONING_EFFORT],
            )
        ]
        self.session = FakeSession(response_text, started, wait)
        self.session.rpc = SimpleNamespace(git_hub_auth=SimpleNamespace(get_status=AsyncMock(
            return_value=SimpleNamespace(is_authenticated=True, login=session_login, auth_type="token"),
        )))
        self.session_options_history = []
        self.session_options = None
        self.session_creation_count = 0
        self.model_list_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def start(self):
        pass

    async def stop(self):
        self.stopped = True

    async def get_auth_status(self):
        return self.auth_status

    async def list_models(self):
        self.model_list_count += 1
        if self.catalog_error:
            raise self.catalog_error
        return self.models

    async def create_session(self, **kwargs):
        if self.request_error:
            raise self.request_error
        self.session_options = kwargs
        self.session_options_history.append(kwargs)
        self.session_creation_count += 1
        return self.session


class GitHubCopilotProviderTests(unittest.TestCase):
    def setUp(self):
        self.app = FakeApp()
        self.provider = GitHubCopilotProvider(self.app)

    def use_client(self, client):
        self.provider._create_client = AsyncMock(return_value=client)

    def test_followup_uses_isolated_session_and_keeps_message_roles(self):
        client = FakeClient()
        self.use_client(client)
        history = [
            {"role": "system", "content": "Answer concisely."},
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Follow-up"},
        ]

        response = self.provider.get_response(
            "Answer concisely.",
            history,
            return_response=True,
        )

        self.assertEqual(response, "Copilot response")
        self.assertEqual(client.session_options["model"], self.provider.MODEL_ID)
        self.assertEqual(
            client.session_options["reasoning_effort"],
            self.provider.REASONING_EFFORT,
        )
        self.assertEqual(client.session_options["available_tools"], [])
        self.assertFalse(client.session_options["enable_config_discovery"])
        self.assertFalse(client.session_options["enable_session_telemetry"])
        self.assertFalse(client.session_options["enable_file_hooks"])
        self.assertFalse(client.session_options["enable_host_git_operations"])
        self.assertFalse(client.session_options["enable_session_store"])
        self.assertFalse(client.session_options["enable_github_cache_store"])
        self.assertFalse(client.session_options["enable_skills"])
        self.assertFalse(client.session_options["enable_on_demand_instruction_discovery"])
        self.assertTrue(client.session_options["skip_custom_instructions"])
        self.assertEqual(
            client.session_options["system_message"],
            {"mode": "replace", "content": "Answer concisely."},
        )
        conversation_json = client.session.prompt.split(
            "Conversation history in JSON:\n",
            maxsplit=1,
        )[1]
        self.assertEqual(
            json.loads(conversation_json),
            history[1:],
        )
        self.assertEqual(client.session.timeout, self.provider.REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(self.app.output_ready_signal.emitted, [])

    def test_inline_response_is_emitted_for_text_replacement(self):
        self.use_client(FakeClient(response_text="  Rewritten text  "))

        response = self.provider.get_response("Rewrite only.", "Rewrite this.")

        self.assertEqual(response, "Rewritten text")
        self.assertEqual(self.app.output_ready_signal.emitted, [("Rewritten text",)])

    def test_connection_check_sends_one_synthetic_request(self):
        client = FakeClient()
        self.use_client(client)

        success, message = self.provider.validate_connection({})

        self.assertTrue(success)
        self.assertIn(self.provider.MODEL_ID, message)
        self.assertIn("alice", message)
        self.assertIn("synthetic prompt", message)
        self.assertEqual(client.session.prompt, "Reply OK.")
        self.assertEqual(self.app.output_ready_signal.emitted, [])
        self.assertEqual(client.model_list_count, 0)
        self.assertEqual(client.session_creation_count, 1)

    def test_connection_check_sends_manually_entered_model_missing_from_catalog(self):
        client = FakeClient(
            models=[
                SimpleNamespace(
                    id="gpt-5.4",
                    supported_reasoning_efforts=["medium"],
                )
            ]
        )
        self.use_client(client)

        success, message = self.provider.validate_connection({})

        self.assertTrue(success)
        self.assertIn(self.provider.MODEL_ID, message)
        self.assertEqual(client.session_creation_count, 1)
        self.assertEqual(client.session_options["model"], self.provider.MODEL_ID)
        self.assertEqual(client.session_options["reasoning_effort"], "medium")
        self.assertEqual(client.session.prompt, "Reply OK.")

    def test_connection_check_sends_effort_even_when_catalog_omits_it(self):
        client = FakeClient(
            models=[
                SimpleNamespace(
                    id=GitHubCopilotProvider.MODEL_ID,
                    supported_reasoning_efforts=["low", "high"],
                )
            ]
        )
        self.use_client(client)

        success, message = self.provider.validate_connection({})

        self.assertTrue(success)
        self.assertEqual(client.session_options["reasoning_effort"], "medium")
        self.assertEqual(client.model_list_count, 0)
        self.assertEqual(client.session_creation_count, 1)

    def test_unauthenticated_account_gets_sign_in_instructions(self):
        client = FakeClient(authenticated=False)
        self.use_client(client)

        success, message = self.provider.validate_connection({})
        response = self.provider.get_response("Rewrite only.", "Rewrite this.")

        self.assertFalse(success)
        self.assertIn("copilot", message.lower())
        self.assertIn(GitHubCopilotProvider.SIGN_IN_GUIDE_URL, message)
        self.assertEqual(response, "")
        self.assertIn("sign-in required", self.app.show_message_signal.emitted[-1][0])
        self.assertEqual(client.model_list_count, 0)
        self.assertEqual(client.session_creation_count, 0)

    def test_cancel_stops_an_active_request_without_showing_an_error(self):
        started = threading.Event()
        self.use_client(FakeClient(started=started, wait=True))
        result = {}
        worker = threading.Thread(
            target=lambda: result.setdefault(
                "response",
                self.provider.get_response("Rewrite only.", "Rewrite this."),
            ),
            daemon=True,
        )

        worker.start()
        self.assertTrue(started.wait(timeout=5))
        self.provider.cancel()
        worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(result["response"], "")
        self.assertEqual(self.app.show_message_signal.emitted, [])

    def test_settings_expose_defaults_and_text_fields_for_custom_ui(self):
        from aiprovider import TextSetting

        settings = {setting.name: setting for setting in self.provider.settings}
        self.assertIsInstance(settings["github_account"], TextSetting)
        self.assertIsInstance(settings["model"], TextSetting)
        self.assertIsInstance(settings["reasoning_effort"], TextSetting)
        self.assertEqual(settings["github_account"].default_value, "")
        self.assertEqual(settings["model"].default_value, "gpt-5-mini")
        self.assertEqual(settings["reasoning_effort"].default_value, "medium")

    def test_explicit_account_passes_only_in_memory_token_to_sdk(self):
        with (
            patch("github_copilot_provider.read_account_token", new_callable=AsyncMock,
                  return_value="test-secret") as read_token,
            patch("copilot.CopilotClient") as client,
        ):
            asyncio.run(self.provider._create_client({"github_account": "alice"}))
        read_token.assert_awaited_once_with("alice")
        client.assert_called_once_with(github_token="test-secret", use_logged_in_user=False)
        self.assertNotIn("test-secret", repr(vars(self.provider)))

    def test_automatic_account_preserves_sdk_authentication_without_gh(self):
        with (
            patch("github_copilot_provider.read_account_token", new_callable=AsyncMock) as read_token,
            patch("copilot.CopilotClient") as client,
        ):
            asyncio.run(self.provider._create_client({"github_account": ""}))
        read_token.assert_not_awaited()
        client.assert_called_once_with(use_logged_in_user=True)

    def test_selected_identity_must_match_before_catalog_or_request(self):
        for login in ("bob", "", None):
            with self.subTest(login=login):
                client = FakeClient(login=login)
                self.use_client(client)
                success, message = self.provider.validate_connection({"github_account": "alice"})
                self.assertFalse(success)
                self.assertIn("does not match", message)
                self.assertIn("alice", message)
                self.assertEqual(client.session_creation_count, 0 if login else 1)
                self.assertIsNone(client.session.prompt)
                self.assertEqual(client.model_list_count, 0)
                self.assertTrue(client.stopped)

    def test_identity_comparison_is_case_insensitive(self):
        self.use_client(FakeClient(login="Alice"))
        self.assertTrue(self.provider.validate_connection({"github_account": "alice"})[0])

    def test_session_identity_used_when_sdk_login_absent(self):
        client = FakeClient(login=None, session_login="alice")
        self.use_client(client)
        success, message = self.provider.validate_connection({"github_account": "alice"})
        self.assertTrue(success)
        self.assertIn("alice", message)
        self.assertEqual(client.session_creation_count, 2)
        self.assertEqual(client.session_options["model"], self.provider.MODEL_ID)
        self.assertEqual(client.session.prompt, "Reply OK.")

    def test_resolved_token_identity_mismatch_never_sends_a_prompt(self):
        client = FakeClient(login=None, session_login="bob")
        self.use_client(client)
        success, message = self.provider.validate_connection({"github_account": "alice"})
        self.assertFalse(success)
        self.assertIn("does not match", message)
        self.assertEqual(client.session_creation_count, 1)
        self.assertIsNone(client.session.prompt)

    def test_session_identity_survives_model_catalog_error(self):
        client = FakeClient(login=None, session_login="alice", catalog_error=RuntimeError("proxy error"))
        self.use_client(client)
        result = self.provider.inspect_connection({"github_account": "alice"})
        self.assertTrue(result["authenticated"])
        self.assertEqual(result["login"], "alice")
        self.assertEqual(result["auth_type"], "token")
        self.assertEqual(result["models"], [])
        self.assertIn("error", result)
        self.assertIsNone(client.session.prompt)

    def test_unsaved_snapshot_is_used_without_mutating_saved_config(self):
        self.provider.load_config({"github_account": "bob", "model": "saved-model"})
        client = FakeClient(models=[SimpleNamespace(id="preview-model", supported_reasoning_efforts=["low"])])
        self.use_client(client)
        config = {"github_account": "alice", "model": "preview-model", "reasoning_effort": "low"}
        original = dict(config)
        success, message = self.provider.validate_connection(config)
        self.assertTrue(success)
        self.assertIn("alice", message)
        self.assertIn("preview-model", message)
        self.assertEqual(client.session_options["model"], "preview-model")
        self.assertEqual(client.session_options["reasoning_effort"], "low")
        self.provider._create_client.assert_awaited_once_with(config)
        self.assertEqual(config, original)
        self.assertEqual(self.provider.github_account, "bob")
        self.assertEqual(self.provider.model, "saved-model")

    def test_writing_uses_saved_account_model_and_effort(self):
        self.provider.load_config({"github_account": "alice", "model": "saved-model", "reasoning_effort": ""})
        client = FakeClient(models=[SimpleNamespace(id="saved-model", supported_reasoning_efforts=["medium"])])
        self.use_client(client)
        self.assertEqual(self.provider.get_response("Rewrite.", "Private selected text", True), "Copilot response")
        self.assertEqual(self.provider._create_client.await_args.args[0]["github_account"], "alice")
        self.assertEqual(client.session_options["model"], "saved-model")
        self.assertNotIn("reasoning_effort", client.session_options)

    def test_reasoning_none_and_models_without_reasoning(self):
        for supported, configured, expected in (
            (None, "medium", "medium"), ([], "medium", "medium"),
            (["low", "medium"], "", None), (["none", "medium"], "none", "none"),
            (["none", "medium"], "", None), (["none", "medium"], "  ", None),
            (["none", "medium"], None, None),
        ):
            with self.subTest(supported=supported, configured=configured):
                client = FakeClient(models=[SimpleNamespace(id=self.provider.MODEL_ID, supported_reasoning_efforts=supported)])
                self.use_client(client)
                self.assertTrue(self.provider.validate_connection({"reasoning_effort": configured})[0])
                self.assertEqual(client.session_options.get("reasoning_effort"), expected)

    def test_literal_none_is_sent_even_when_catalog_omits_it(self) -> None:
        client = FakeClient(models=[SimpleNamespace(
            id=self.provider.MODEL_ID, supported_reasoning_efforts=["low", "medium"],
        )])
        self.use_client(client)
        success, message = self.provider.validate_connection({"reasoning_effort": "none"})
        self.assertTrue(success)
        self.assertEqual(client.session_options["reasoning_effort"], "none")
        self.assertEqual(client.model_list_count, 0)
        self.assertEqual(client.session_creation_count, 1)

    def test_inspection_returns_identity_and_model_options_without_prompt(self):
        client = FakeClient(models=[SimpleNamespace(id="model-a", name="Model A", supported_reasoning_efforts=["low", "medium"])])
        self.use_client(client)
        result = self.provider.inspect_connection({"github_account": "alice"})
        self.assertEqual(result, {"authenticated": True, "login": "alice", "auth_type": "token",
                                  "models": [{"id": "model-a", "name": "Model A", "reasoning_efforts": ["low", "medium"]}]})
        self.assertEqual(client.session_creation_count, 0)

    def test_partial_auth_survives_catalog_error_and_timeout(self):
        for error in (RuntimeError("proxy <html>secret</html>"), TimeoutError()):
            with self.subTest(error=type(error).__name__):
                self.use_client(FakeClient(catalog_error=error))
                result = self.provider.inspect_connection({"github_account": "alice"})
                self.assertTrue(result["authenticated"])
                self.assertEqual(result["login"], "alice")
                self.assertEqual(result["auth_type"], "token")
                self.assertEqual(result["models"], [])
                self.assertIn("error", result)
                self.assertNotIn("secret", result["error"])

    def test_catalog_timeout_preserves_verified_identity(self):
        client = FakeClient()

        async def hang():
            await asyncio.Event().wait()

        client.list_models = hang
        self.use_client(client)
        self.provider.CONNECTION_TIMEOUT_SECONDS = 0.01
        result = self.provider.inspect_connection({"github_account": "alice"})
        self.assertTrue(result["authenticated"])
        self.assertEqual(result["login"], "alice")
        self.assertIn("timed out", result["error"])
        self.assertTrue(client.stopped)

    def test_cancel_inspection_preserves_identity_and_stops_client(self):
        started = threading.Event()
        client = FakeClient()

        async def hang():
            started.set()
            await asyncio.Event().wait()

        client.list_models = hang
        self.use_client(client)
        result = {}
        worker = threading.Thread(target=lambda: result.update(self.provider.inspect_connection({})))
        worker.start()
        self.assertTrue(started.wait(5))
        self.provider.cancel()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertTrue(result["authenticated"])
        self.assertEqual(result["login"], "alice")
        self.assertIn("cancelled", result["error"])
        self.assertTrue(client.stopped)

    def test_inspection_exposes_mismatch_as_unauthenticated(self):
        self.use_client(FakeClient(login="bob"))
        result = self.provider.inspect_connection({"github_account": "alice"})
        self.assertFalse(result["authenticated"])
        self.assertEqual(result["login"], "bob")
        self.assertIn("does not match", result["error"])

    def test_integration_rejection_is_not_treated_as_catalog_success(self):
        for term in ("integration", "integrator"):
            with self.subTest(term=term):
                self.use_client(FakeClient(request_error=RuntimeError(f"model is not supported for this {term}")))
                success, message = self.provider.validate_connection({"github_account": "alice"})
                self.assertFalse(success)
                self.assertIn("SDK integration", message)
                self.assertIn("alice", message)
                self.assertIn(self.provider.MODEL_ID, message)

    def test_blocked_catalog_still_sends_exactly_one_synthetic_prompt(self) -> None:
        for effort in ("", "none", "medium"):
            with self.subTest(effort=effort):
                client = FakeClient(catalog_error=RuntimeError("<html>web-filter secret</html>"))
                client.session.send_and_wait = AsyncMock(wraps=client.session.send_and_wait)
                self.use_client(client)
                success, message = self.provider.validate_connection({
                    "github_account": "alice", "model": "manually-entered", "reasoning_effort": effort,
                })
                self.assertTrue(success)
                self.assertNotIn("secret", message)
                self.assertEqual(client.model_list_count, 0)
                self.assertEqual(client.session_options["model"], "manually-entered")
                if effort:
                    self.assertEqual(client.session_options["reasoning_effort"], effort)
                else:
                    self.assertNotIn("reasoning_effort", client.session_options)
                client.session.send_and_wait.assert_awaited_once_with(
                    "Reply OK.", timeout=self.provider.REQUEST_TIMEOUT_SECONDS,
                )

    def test_writing_never_calls_hanging_catalog_with_saved_settings(self) -> None:
        client = FakeClient()

        async def hang() -> None:
            await asyncio.Event().wait()

        client.list_models = AsyncMock(side_effect=hang)
        self.use_client(client)
        self.provider.CONNECTION_TIMEOUT_SECONDS = 0.01
        self.provider.load_config({"github_account": "alice", "model": "manual-model", "reasoning_effort": "high"})
        response = self.provider.get_response("Rewrite.", "Selected text", True)
        self.assertEqual(response, "Copilot response")
        self.assertEqual(client.session_options["model"], "manual-model")
        self.assertEqual(client.session_options["reasoning_effort"], "high")
        self.assertEqual(client.session.prompt, "Selected text")
        client.list_models.assert_not_awaited()

    def test_manual_model_blank_omits_reasoning_and_none_is_literal(self) -> None:
        for effort in ("", "none"):
            with self.subTest(effort=effort):
                client = FakeClient(models=[])
                self.use_client(client)
                self.assertTrue(self.provider.validate_connection({
                    "model": "manual-model", "reasoning_effort": effort,
                })[0])
                self.assertEqual(client.session_options["model"], "manual-model")
                if effort:
                    self.assertEqual(client.session_options["reasoning_effort"], "none")
                else:
                    self.assertNotIn("reasoning_effort", client.session_options)

    def test_auth_cancellation_prevents_sending(self) -> None:
        client = FakeClient()
        client.get_auth_status = AsyncMock(side_effect=asyncio.CancelledError())
        self.use_client(client)
        success, message = self.provider.validate_connection({})
        self.assertFalse(success)
        self.assertIn("cancelled", message)
        self.assertEqual(client.session_creation_count, 0)
        self.assertIsNone(client.session.prompt)

    def test_request_errors_never_log_or_display_raw_secrets_or_html(self):
        for detail, expected in (("401 secret-credential", "denied access"),
                                 ("502 <html>secret-credential</html>", "network")):
            with self.subTest(detail=expected):
                self.use_client(FakeClient(request_error=RuntimeError(detail)))
                with self.assertLogs(level="ERROR") as logs:
                    self.assertEqual(self.provider.get_response("Rewrite.", "Private text"), "")
                output = str(logs.output) + str(self.app.show_message_signal.emitted[-1])
                self.assertNotIn("secret-credential", output)
                self.assertNotIn("<html>", output)
                self.assertIn(expected, output)

    def test_connection_stage_is_bounded_and_client_stopped(self):
        client = FakeClient()

        async def hang():
            await asyncio.Event().wait()

        client.get_auth_status = hang
        self.use_client(client)
        self.provider.CONNECTION_TIMEOUT_SECONDS = 0.01
        success, message = self.provider.validate_connection({})
        self.assertFalse(success)
        self.assertIn("timed out", message)
        self.assertTrue(client.stopped)

    def test_cleanup_failure_does_not_mask_integration_error(self):
        client = FakeClient(request_error=RuntimeError("model unsupported for integration"))
        client.stop = AsyncMock(side_effect=RuntimeError("secret cleanup"))
        client.force_stop = AsyncMock()
        self.use_client(client)
        success, message = self.provider.validate_connection({})
        self.assertFalse(success)
        self.assertIn("SDK integration", message)
        self.assertNotIn("secret", message)
        client.force_stop.assert_awaited_once()

    def test_cancellation_during_validation_is_not_reported_as_cleanup_error(self):
        started = threading.Event()
        client = FakeClient(started=started, wait=True)
        client.session.disconnect = AsyncMock(side_effect=RuntimeError("secret cleanup"))
        self.use_client(client)
        result = {}
        worker = threading.Thread(target=lambda: result.setdefault("validation", self.provider.validate_connection({})))
        worker.start()
        self.assertTrue(started.wait(5))
        self.provider.cancel()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertFalse(result["validation"][0])
        self.assertIn("cancelled", result["validation"][1])

    def test_empty_validation_response_is_failure(self):
        self.use_client(FakeClient(response_text=" "))
        success, message = self.provider.validate_connection({})
        self.assertFalse(success)
        self.assertIn("no text", message)

    def test_list_accounts_uses_cancellable_stored_account_reader(self):
        with patch("github_copilot_provider.list_stored_accounts", new_callable=AsyncMock,
                   return_value=["alice", "bob"]) as accounts:
            self.assertEqual(self.provider.list_accounts(), ["alice", "bob"])
            accounts.assert_awaited_once()

    def test_account_listing_failure_does_not_block_automatic_inspection(self) -> None:
        from copilot_connection import CopilotConnectionError

        client = FakeClient()
        self.use_client(client)
        with patch("github_copilot_provider.list_stored_accounts", new_callable=AsyncMock,
                   side_effect=CopilotConnectionError("GitHub CLI unavailable")) as accounts:
            with self.assertRaises(CopilotConnectionError):
                self.provider.list_accounts()
            result = self.provider.inspect_connection({"github_account": ""})
            accounts.assert_awaited_once()
        self.assertTrue(result["authenticated"])
        self.assertEqual(result["login"], "alice")
        self.assertNotIn("error", result)
        self.assertEqual(client.session_creation_count, 0)
        self.assertIsNone(client.session.prompt)


if __name__ == "__main__":
    unittest.main()
