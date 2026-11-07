"""Testy převodu datových struktur a adaptérů LLM."""

import json
import unittest
from unittest.mock import MagicMock, patch

from agent.groq_client import GroqClient
from agent.llm_client import LLMError, OllamaClient
from agent.models import ChatMessage, LLMRequest, ToolCall, ToolDefinition


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

    @patch("agent.llm_client.urlopen")
    def test_rejects_non_dictionary_json_response(self, mock_urlopen) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'[]'
        mock_urlopen.return_value = response
        with self.assertRaises(LLMError):
            self.client.chat(LLMRequest(messages=[]))


if __name__ == "__main__":
    unittest.main()
