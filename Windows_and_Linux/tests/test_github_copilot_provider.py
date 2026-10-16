import asyncio
import json
import threading
import unittest
from types import SimpleNamespace

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
    ):
        self.auth_status = SimpleNamespace(
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
        self.session_options = None
        self.session_creation_count = 0
        self.model_list_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get_auth_status(self):
        return self.auth_status

    async def list_models(self):
        self.model_list_count += 1
        return self.models

    async def create_session(self, **kwargs):
        self.session_options = kwargs
        self.session_creation_count += 1
        return self.session


class GitHubCopilotProviderTests(unittest.TestCase):
    def setUp(self):
        self.app = FakeApp()
        self.provider = GitHubCopilotProvider(self.app)

    def use_client(self, client):
        self.provider._create_client = lambda: client

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

    def test_connection_check_confirms_model_without_sending_a_request(self):
        client = FakeClient()
        self.use_client(client)

        success, message = self.provider.validate_connection({})

        self.assertTrue(success)
        self.assertIn(self.provider.MODEL_NAME, message)
        self.assertIn("medium", message)
        self.assertIn("no model request", message.lower())
        self.assertEqual(client.model_list_count, 1)
        self.assertEqual(client.session_creation_count, 0)

    def test_connection_check_reports_when_model_is_not_available(self):
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

        self.assertFalse(success)
        self.assertIn(self.provider.MODEL_NAME, message)
        self.assertIn("not currently listed", message)
        self.assertEqual(client.session_creation_count, 0)

    def test_connection_check_reports_when_medium_effort_is_not_available(self):
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

        self.assertFalse(success)
        self.assertIn("medium reasoning effort", message)
        self.assertEqual(client.session_creation_count, 0)

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


if __name__ == "__main__":
    unittest.main()
