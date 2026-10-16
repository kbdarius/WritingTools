import unittest
from unittest.mock import patch

from azure_usage import F0_MONTHLY_CHARACTERS, get_speech_usage


class AzureUsageTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "azure_speech": {
                "resource_id": (
                    "/subscriptions/test/resourceGroups/test/providers/"
                    "Microsoft.CognitiveServices/accounts/speech-test"
                )
            }
        }

    def test_unavailable_metric_explains_that_speech_playback_is_unaffected(self):
        error = (
            "ERROR: (BadRequest) Failed to find metric configuration for provider: "
            "Microsoft.CognitiveServices, resource Type: accounts, metric: "
            "SynthesizedCharacters, Valid metrics: TotalCalls"
        )
        with (
            patch("azure_usage.azure_cli_path", return_value="az"),
            patch(
                "azure_usage._run_cli",
                side_effect=[{"id": "test"}, RuntimeError(error)],
            ) as run_cli,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Speech playback is unaffected",
            ) as raised:
                get_speech_usage(self.config)

        self.assertIn("cannot calculate monthly character totals", str(raised.exception))
        self.assertEqual(run_cli.call_count, 2)

    def test_other_metric_errors_are_preserved(self):
        with (
            patch("azure_usage.azure_cli_path", return_value="az"),
            patch(
                "azure_usage._run_cli",
                side_effect=[{"id": "test"}, RuntimeError("Azure Monitor is unavailable")],
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Azure Monitor is unavailable"):
                get_speech_usage(self.config)

    def test_available_metric_still_returns_character_and_f0_quota_totals(self):
        metric = {
            "value": [
                {
                    "timeseries": [
                        {
                            "data": [
                                {"total": 123},
                                {"total": 456},
                            ]
                        }
                    ]
                }
            ]
        }
        with (
            patch("azure_usage.azure_cli_path", return_value="az"),
            patch(
                "azure_usage._run_cli",
                side_effect=[{"id": "test"}, metric, "F0"],
            ) as run_cli,
        ):
            usage = get_speech_usage(self.config)

        self.assertEqual(usage["characters"], 579)
        self.assertEqual(usage["quota"], F0_MONTHLY_CHARACTERS)
        metric_args = run_cli.call_args_list[1].args
        self.assertEqual(
            metric_args[metric_args.index("--metric") + 1],
            "SynthesizedCharacters",
        )
