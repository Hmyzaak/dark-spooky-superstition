"""Testy hlavního rozhodovacího cyklu AI agenta."""

import tempfile
import unittest
from pathlib import Path

from agent.agent import AIAgent
from agent.llm_client import LLMError
from agent.memory import AgentMemory
from agent.mock_llm_client import MockLLMClient


class TestAIAgent(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "test_memory.db"
        self.memory = AgentMemory(database_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_returns_direct_model_answer(self) -> None:
        client = MockLLMClient(
            [{"message": {"role": "assistant", "content": "Ahoj!"}}]
        )
        agent = AIAgent(llm_client=client, memory=self.memory)

        result = agent.run("Pozdrav mě.")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.answer, "Ahoj!")
        self.assertEqual(result.tool_calls, 0)
        self.assertEqual(len(client.calls), 1)

    def test_executes_tool_and_returns_follow_up_answer(self) -> None:
        client = MockLLMClient(
            [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "calculator",
                                    "arguments": {
                                        "operation": "multiply",
                                        "a": 125,
                                        "b": 8,
                                    },
                                }
                            }
                        ],
                    }
                },
                {
                    "message": {
                        "role": "assistant",
                        "content": "Výsledek je 1000.",
                    }
                },
            ]
        )
        agent = AIAgent(llm_client=client, memory=self.memory)

        result = agent.run("Kolik je 125 krát 8?")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.answer, "Výsledek je 1000.")
        self.assertEqual(result.tool_calls, 1)
        self.assertEqual(len(client.calls), 2)
        second_call_messages = client.calls[1]["messages"]
        self.assertTrue(any(message["role"] == "tool" for message in second_call_messages))


    def test_handles_tool_arguments_as_json_text(self) -> None:
        client = MockLLMClient(
            [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "calculator",
                                    "arguments": '{"operation":"add","a":2,"b":3}',
                                }
                            }
                        ],
                    }
                },
                {"message": {"role": "assistant", "content": "Výsledek je 5."}},
            ]
        )
        agent = AIAgent(llm_client=client, memory=self.memory)

        result = agent.run("Kolik je 2 + 3?")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.tool_calls, 1)
        self.assertEqual(result.answer, "Výsledek je 5.")

    def test_rejects_empty_user_input(self) -> None:
        client = MockLLMClient([])
        agent = AIAgent(llm_client=client, memory=self.memory)

        result = agent.run("   ")

        self.assertEqual(result.status, "error")
        self.assertEqual(len(client.calls), 0)

    def test_handles_llm_error(self) -> None:
        class FailingClient:
            def chat(self, messages, tools=None):
                raise LLMError("Simulovaná chyba spojení.")

        agent = AIAgent(llm_client=FailingClient(), memory=self.memory)

        result = agent.run("Test spojení")

        self.assertEqual(result.status, "error")
        self.assertIn("Simulovaná chyba spojení", result.error)

    def test_handles_invalid_model_response(self) -> None:
        client = MockLLMClient([{"unexpected": "structure"}])
        agent = AIAgent(llm_client=client, memory=self.memory)

        result = agent.run("Test neplatné odpovědi")

        self.assertEqual(result.status, "error")
        self.assertIn("message", result.error)

    def test_mock_client_reports_exhausted_responses(self) -> None:
        client = MockLLMClient([])

        with self.assertRaises(LLMError):
            client.chat(messages=[])


if __name__ == "__main__":
    unittest.main()
