"""Testy převodu datových struktur a adaptérů LLM."""

import json
import unittest
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import MagicMock, patch

from agent.groq_client import GroqClient
from agent.llm_client import (
    LLMError,
    OllamaClient,
    RateLimitError,
    ToolValidationError,
)
from agent.models import ChatMessage, LLMRequest, ToolCall, ToolDefinition
from agent.retry import (
    MAX_HTTP_TIMEOUT_SECONDS,
    MAX_RETRIES,
    MAX_RETRY_DELAY_SECONDS,
    get_retry_delay,
    is_retryable_http_status,
    validate_http_settings,
)


def make_http_error(status_code: int, retry_after: str | None = None) -> HTTPError:
    """Vytvoří HTTPError vhodný pro testování opakování požadavků."""

    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    body = b'{"error": {"message": "temporary failure"}}'
    return HTTPError(
        "https://example.test/api", status_code, "Test error", headers, BytesIO(body)
    )


def make_groq_error(status_code: int, message: str, code: str | None = None) -> HTTPError:
    headers = Message()
    body = json.dumps({"error": {"message": message, "code": code}}).encode()
    return HTTPError(
        "https://example.test/api", status_code, "Test error", headers, BytesIO(body)
    )


def make_http_response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(payload).encode(
        "utf-8"
    )
    return response


class TestGroqClient(unittest.TestCase):
    def setUp(self) -> None:
        self.client = GroqClient(api_key="test-key", max_retries=0)

    def test_converts_internal_request_to_openai_compatible_payload(self) -> None:
        request = LLMRequest(
            messages=[
                ChatMessage(role="system", content="Instrukce"),
                ChatMessage(role="assistant", tool_calls=[
                    ToolCall("call-1", "calculator", {"a": 2})
                ]),
                ChatMessage(
                    role="tool",
                    content='{"result": 2}',
                    tool_call_id="call-1",
                    name="calculator",
                ),
            ],
            tools=[ToolDefinition("calculator", "Počítá", {"type": "object"})],
        )

        payload = {
            "model": self.client.model,
            "messages": [self.client._message_to_groq(item) for item in request.messages],
            "tools": [self.client._tool_to_groq(item) for item in request.tools],
        }
        self.assertEqual(payload["messages"][1]["tool_calls"][0]["id"], "call-1")
        self.assertEqual(payload["messages"][2]["tool_call_id"], "call-1")
        self.assertEqual(payload["tools"][0]["function"]["name"], "calculator")

    @patch("agent.groq_client.urlopen")
    def test_parses_groq_response(self, mock_urlopen) -> None:
        response_body = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call-abc",
                        "function": {
                            "name": "calculator",
                            "arguments": '{"operation":"add","a":2,"b":3}',
                        },
                    }],
                }
            }]
        }
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(response_body).encode()
        mock_urlopen.return_value = response

        result = self.client.chat(LLMRequest(messages=[]))
        self.assertIsNone(result.content)
        self.assertEqual(result.tool_calls[0].id, "call-abc")
        self.assertEqual(result.tool_calls[0].arguments["a"], 2)

    @patch("agent.groq_client.urlopen", side_effect=ConnectionResetError("connection reset"))
    def test_converts_unexpected_network_oserror_to_llm_error(self, mock_urlopen) -> None:
        with self.assertRaises(LLMError):
            self.client.chat(LLMRequest(messages=[]))

    @patch("agent.groq_client.time.sleep")
    @patch("agent.groq_client.urlopen")
    def test_retries_network_timeout(self, mock_urlopen, mock_sleep) -> None:
        client = GroqClient(api_key="test-key", max_retries=1)
        mock_urlopen.side_effect = [
            TimeoutError("request timed out"),
            make_http_response({"choices": [{"message": {"content": "Hotovo"}}]}),
        ]

        result = client.chat(LLMRequest(messages=[]))

        self.assertEqual(result.content, "Hotovo")
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(1.0)

    @patch("agent.groq_client.time.sleep")
    @patch("agent.groq_client.urlopen")
    def test_retries_rate_limit_and_respects_retry_after(self, mock_urlopen, mock_sleep) -> None:
        client = GroqClient(api_key="test-key", max_retries=1)
        mock_urlopen.side_effect = [
            make_http_error(429, retry_after="3"),
            make_http_response({"choices": [{"message": {"content": "Hotovo"}}]}),
        ]

        result = client.chat(LLMRequest(messages=[]))

        self.assertEqual(result.content, "Hotovo")
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(3.0)

    @patch("agent.groq_client.time.sleep")
    @patch("agent.groq_client.urlopen", side_effect=make_http_error(401))
    def test_does_not_retry_permanent_http_error(self, mock_urlopen, mock_sleep) -> None:
        client = GroqClient(api_key="test-key", max_retries=2)

        with self.assertRaises(LLMError):
            client.chat(LLMRequest(messages=[]))

        mock_urlopen.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("agent.groq_client.time.sleep")
    @patch("agent.groq_client.urlopen", side_effect=make_groq_error(
        400, "Tool call validation failed", "tool_use_failed"
    ))
    def test_tool_validation_error_is_not_retried(self, mock_urlopen, mock_sleep) -> None:
        client = GroqClient(api_key="test-key", max_retries=2)

        with self.assertRaises(ToolValidationError):
            client.chat(LLMRequest(messages=[]))

        mock_urlopen.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("agent.groq_client.time.sleep")
    @patch("agent.groq_client.urlopen")
    def test_retries_groq_tpm_http_413(self, mock_urlopen, mock_sleep) -> None:
        client = GroqClient(api_key="test-key", max_retries=1)
        mock_urlopen.side_effect = [
            make_groq_error(413, "Request too large for tokens per minute (TPM)"),
            make_http_response({"choices": [{"message": {"content": "Hotovo"}}]}),
        ]

        result = client.chat(LLMRequest(messages=[]))

        self.assertEqual(result.content, "Hotovo")
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(10.0)

    @patch("agent.groq_client.time.sleep")
    @patch(
        "agent.groq_client.urlopen",
        side_effect=[
            make_groq_error(413, "Request exceeds tokens per minute (TPM)"),
            make_groq_error(413, "Request exceeds tokens per minute (TPM)"),
        ],
    )
    def test_reports_tpm_error_after_retry_budget_is_exhausted(
        self, mock_urlopen, mock_sleep
    ) -> None:
        client = GroqClient(api_key="test-key", max_retries=1)

        with self.assertRaises(RateLimitError):
            client.chat(LLMRequest(messages=[]))

        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(10.0)

    @patch("agent.groq_client.urlopen", side_effect=make_groq_error(
        413, "Payload too large"
    ))
    def test_does_not_classify_generic_http_413_as_rate_limit(self, mock_urlopen) -> None:
        from agent.llm_client import ProviderError

        with self.assertRaises(ProviderError):
            self.client.chat(LLMRequest(messages=[]))

    def test_requires_api_key(self) -> None:
        with patch("agent.groq_client.GROQ_API_KEY", ""):
            with self.assertRaises(ValueError):
                GroqClient(api_key="")

    @patch("agent.groq_client.urlopen")
    def test_rejects_malformed_response(self, mock_urlopen) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"unexpected": true}'
        mock_urlopen.return_value = response
        with self.assertRaises(LLMError):
            self.client.chat(LLMRequest(messages=[]))


class TestOllamaClient(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OllamaClient(max_retries=0)

    def test_converts_internal_tool_call_and_tool_result(self) -> None:
        from agent.llm_client import _message_to_ollama

        assistant = ChatMessage(
            role="assistant",
            tool_calls=[ToolCall("internal-id", "calculator", {"a": 1})],
        )
        tool_result = ChatMessage(
            role="tool", content='{"result": 1}', name="calculator", tool_call_id="internal-id"
        )
        converted_assistant = _message_to_ollama(assistant)
        converted_tool = _message_to_ollama(tool_result)

        self.assertEqual(
            converted_assistant["tool_calls"][0]["function"]["name"], "calculator"
        )
        self.assertEqual(converted_tool["tool_name"], "calculator")

    @patch("agent.llm_client.urlopen")
    def test_parses_response_and_generates_missing_tool_call_id(self, mock_urlopen) -> None:
        response_body = {
            "message": {
                "content": None,
                "tool_calls": [{
                    "function": {
                        "name": "calculator",
                        "arguments": {"operation": "add", "a": 1, "b": 2},
                    }
                }],
            }
        }
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(response_body).encode()
        mock_urlopen.return_value = response

        result = self.client.chat(LLMRequest(messages=[]))
        self.assertEqual(result.tool_calls[0].id, "ollama-call-1")
        self.assertEqual(result.tool_calls[0].name, "calculator")

    @patch("agent.llm_client.urlopen", side_effect=ConnectionResetError("connection reset"))
    def test_converts_network_oserror_to_llm_error(self, mock_urlopen) -> None:
        with self.assertRaises(LLMError):
            self.client.chat(LLMRequest(messages=[]))

    @patch("agent.llm_client.time.sleep")
    @patch("agent.llm_client.urlopen")
    def test_retries_service_unavailable(self, mock_urlopen, mock_sleep) -> None:
        client = OllamaClient(max_retries=1)
        mock_urlopen.side_effect = [
            make_http_error(503),
            make_http_response({"message": {"content": "Hotovo"}}),
        ]

        result = client.chat(LLMRequest(messages=[]))

        self.assertEqual(result.content, "Hotovo")
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once_with(1.0)

    @patch("agent.llm_client.time.sleep")
    @patch("agent.llm_client.urlopen", side_effect=make_http_error(400))
    def test_does_not_retry_bad_request(self, mock_urlopen, mock_sleep) -> None:
        client = OllamaClient(max_retries=2)

        with self.assertRaises(LLMError):
            client.chat(LLMRequest(messages=[]))

        mock_urlopen.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("agent.llm_client.urlopen")
    def test_rejects_non_dictionary_json_response(self, mock_urlopen) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'[]'
        mock_urlopen.return_value = response
        with self.assertRaises(LLMError):
            self.client.chat(LLMRequest(messages=[]))


class TestRetryPolicy(unittest.TestCase):
    def test_only_temporary_http_statuses_are_retryable(self) -> None:
        self.assertTrue(is_retryable_http_status(408))
        self.assertTrue(is_retryable_http_status(429))
        self.assertTrue(is_retryable_http_status(503))
        self.assertFalse(is_retryable_http_status(400))
        self.assertFalse(is_retryable_http_status(401))

    def test_retry_delay_uses_exponential_backoff_and_cap(self) -> None:
        self.assertEqual(get_retry_delay(0), 1.0)
        self.assertEqual(get_retry_delay(1), 2.0)
        self.assertEqual(get_retry_delay(10), float(MAX_RETRY_DELAY_SECONDS))
        self.assertEqual(get_retry_delay(0, base_delay=10), 10.0)
        self.assertEqual(get_retry_delay(1, base_delay=10), 20.0)

    def test_retry_after_is_used_and_capped(self) -> None:
        self.assertEqual(get_retry_delay(0, "4"), 4.0)
        self.assertEqual(
            get_retry_delay(0, str(MAX_RETRY_DELAY_SECONDS + 100)),
            float(MAX_RETRY_DELAY_SECONDS),
        )

    def test_invalid_retry_after_uses_backoff(self) -> None:
        self.assertEqual(get_retry_delay(1, "not-a-delay"), 2.0)

    def test_http_settings_are_bounded_and_validated(self) -> None:
        validate_http_settings(timeout=10, max_retries=MAX_RETRIES)
        for timeout, retries in [
            (0, 1),
            (float("inf"), 1),
            (MAX_HTTP_TIMEOUT_SECONDS + 1, 1),
            (10, -1),
            (10, MAX_RETRIES + 1),
            (10, 1.5),
        ]:
            with self.subTest(timeout=timeout, retries=retries):
                with self.assertRaises(ValueError):
                    validate_http_settings(timeout, retries)


if __name__ == "__main__":
    unittest.main()
