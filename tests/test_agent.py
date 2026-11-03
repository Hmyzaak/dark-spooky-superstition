# tests/test_agent.py
"""Testy hlavního rozhodovacího cyklu AI agenta."""

import tempfile
import unittest
from pathlib import Path

from agent.agent import AIAgent
from agent.llm_client import LLMError
from agent.memory import AgentMemory
from agent.mock_llm_client import MockLLMClient
from config import MAX_AGENT_STEPS


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

    def test_handles_empty_final_answer(self) -> None:
        """Ověří, že prázdná odpověď modelu není považována za úspěch."""

        client = MockLLMClient(
            [{"message": {"role": "assistant", "content": ""}}]
        )
        agent = AIAgent(llm_client=client, memory=self.memory)

        result = agent.run("Odpověz na testovací otázku.")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.tool_calls, 0)
        self.assertIsNotNone(result.error)

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

    def test_executes_multiple_tools_before_follow_up_answer(self) -> None:
        """
        Ověří zpracování více požadavků na nástroje v jednom cyklu Agent Loop.

        Simulovaný LLM požaduje dvě operace kalkulačky:
        1. Sečtení čísel 2 + 3.
        2. Vynásobení čísel 4 * 5.

        Agent musí:
        - provést oba požadované nástroje,
        - zaznamenat oba výsledky do konverzačního kontextu,
        - předat aktualizovaný kontext zpět jazykovému modelu,
        - přijmout jeho finální odpověď.

        Test ověřuje také počet volání LLM a počet provedených nástrojů.
        """

        # Připravíme dvě simulované odpovědi jazykového modelu.
        responses = [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "calculator",
                                "arguments": {
                                    "operation": "add",
                                    "a": 2,
                                    "b": 3,
                                },
                            }
                        },
                        {
                            "function": {
                                "name": "calculator",
                                "arguments": {
                                    "operation": "multiply",
                                    "a": 4,
                                    "b": 5,
                                },
                            }
                        },
                    ],
                }
            },
            {
                "message": {
                    "role": "assistant",
                    "content": "Výsledky jsou 5 a 20.",
                }
            },
        ]

        # Vytvoříme simulovaný LLM klient a instanci agenta.
        client = MockLLMClient(responses)
        agent = AIAgent(llm_client=client, memory=self.memory)

        # Spustíme agenta s požadavkem na dvě matematické operace.
        result = agent.run(
            "Sečti 2 + 3 a zároveň vynásob 4 * 5."
        )

        # Ověříme správné dokončení úkolu.
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.answer, "Výsledky jsou 5 a 20.")

        # Agent musí zaznamenat obě provedená volání nástrojů.
        self.assertEqual(result.tool_calls, 2)

        # LLM musí být zavolán dvakrát:
        # poprvé pro rozhodnutí a podruhé pro finální odpověď.
        self.assertEqual(len(client.calls), 2)

        # Zkontrolujeme kontext předaný LLM při druhém volání.
        second_call_messages = client.calls[1]["messages"]

        # Z kontextu vybereme všechny zprávy obsahující výsledky nástrojů.
        tool_messages = [
            message
            for message in second_call_messages
            if message["role"] == "tool"
        ]

        # Oba výsledky musí být součástí kontextu.
        self.assertEqual(len(tool_messages), 2)

        # Ověříme, že oba požadavky byly zpracovány kalkulačkou.
        self.assertTrue(
            all(
                message["tool_name"] == "calculator"
                for message in tool_messages
            )
        )

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

    def test_stops_when_maximum_agent_steps_is_reached(self) -> None:
        # Připravíme opakující se požadavek na použití kalkulačky.
        responses = []

        for _ in range(MAX_AGENT_STEPS):
            responses.append(
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "calculator",
                                    "arguments": {
                                        "operation": "add",
                                        "a": 1,
                                        "b": 1,
                                    },
                                }
                            }
                        ],
                    }
                }
            )

        client = MockLLMClient(responses)
        agent = AIAgent(llm_client=client, memory=self.memory)

        result = agent.run("Opakovaně počítej 1 + 1.")

        # Agent musí skončit po dosažení maximálního počtu cyklů.
        self.assertEqual(result.status, "limit_reached")   # Agent správně rozpoznal dosažení limitu.
        self.assertEqual(result.tool_calls, MAX_AGENT_STEPS)   # Agent provedl přesně povolený počet volání nástrojů.
        self.assertEqual(len(client.calls), MAX_AGENT_STEPS)   # Agent nepřekročil povolený počet volání LLM.


if __name__ == "__main__":
    unittest.main()
