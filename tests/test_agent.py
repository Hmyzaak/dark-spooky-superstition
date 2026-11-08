"""Testy agentního cyklu nad provider-neutrálním datovým kontraktem."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from agent.agent import AIAgent, AgentResult, to_json
from agent.llm_client import LLMError
from agent.memory import AgentMemory
from agent.mock_llm_client import MockLLMClient
from agent.models import ChatMessage, LLMRequest, LLMResponse, ToolCall
from config import MAX_AGENT_STEPS, SYSTEM_PROMPT


class TestAIAgent(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory = AgentMemory(Path(self.temp_dir.name) / "memory.db")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_agent(self, responses):
        client = MockLLMClient(responses)
        return AIAgent(llm_client=client, memory=self.memory), client

    def test_returns_direct_model_answer(self) -> None:
        agent, client = self.make_agent([LLMResponse(content="Ahoj!")])
        result = agent.run("Pozdrav mě.")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.answer, "Ahoj!")
        self.assertEqual(result.tool_calls, 0)
        self.assertEqual(len(client.calls), 1)
        self.assertIsInstance(client.calls[0], LLMRequest)
        self.assertEqual(client.calls[0].messages[-1].content, "Pozdrav mě.")

    def test_system_prompt_defines_answer_quality_and_verification_limits(self) -> None:
        agent, client = self.make_agent([LLMResponse(content="Rozumím.")])
        result = agent.run("Jak máš zacházet s nejistými informacemi?")

        self.assertEqual(result.status, "completed")
        system_message = client.calls[0].messages[0]
        self.assertEqual(system_message.role, "system")
        self.assertTrue(system_message.content.startswith(SYSTEM_PROMPT))
        self.assertIn("Katalog schopností AI agenta", system_message.content)
        self.assertIn("### `calculator`", system_message.content)
        self.assertIn("Internetové vyhledávání** — NEIMPLEMENTOVÁNO", system_message.content)
        self.assertIn("Nemáš přístup k internetu", SYSTEM_PROMPT)
        self.assertIn("nezávisle ověřil", SYSTEM_PROMPT)
        self.assertIn("Nevymýšlej si fakta", SYSTEM_PROMPT)
        self.assertIn("zohledni všechny výsledky", SYSTEM_PROMPT)

    def test_handles_empty_final_answer(self) -> None:
        agent, _ = self.make_agent([LLMResponse(content="  ")])
        result = agent.run("Odpověz na testovací otázku.")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.tool_calls, 0)
        self.assertIsNotNone(result.error)

    def test_executes_tool_and_returns_follow_up_answer(self) -> None:
        call = ToolCall(
            id="call-1",
            name="calculator",
            arguments={"operation": "multiply", "a": 125, "b": 8},
        )
        agent, client = self.make_agent(
            [LLMResponse(tool_calls=[call]), LLMResponse(content="Výsledek je 1000.")]
        )
        result = agent.run("Kolik je 125 krát 8?")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.answer, "Výsledek je 1000.")
        self.assertEqual(result.tool_calls, 1)
        self.assertEqual(len(client.calls), 2)
        tool_messages = [
            message for message in client.calls[1].messages if message.role == "tool"
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(tool_messages[0].tool_call_id, "call-1")
        self.assertEqual(tool_messages[0].name, "calculator")
        self.assertEqual(json.loads(tool_messages[0].content)["result"], 1000.0)

    def test_executes_multiple_tools_in_one_cycle(self) -> None:
        calls = [
            ToolCall("call-1", "calculator", {"operation": "add", "a": 2, "b": 3}),
            ToolCall(
                "call-2", "calculator", {"operation": "multiply", "a": 4, "b": 5}
            ),
        ]
        agent, client = self.make_agent(
            [LLMResponse(tool_calls=calls), LLMResponse(content="Výsledky jsou 5 a 20.")]
        )
        result = agent.run("Sečti 2 + 3 a vynásob 4 * 5.")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.tool_calls, 2)
        self.assertEqual(len(client.calls), 2)
        second_messages = client.calls[1].messages
        self.assertEqual(
            [message.tool_call_id for message in second_messages if message.role == "tool"],
            ["call-1", "call-2"],
        )
        assistant_tool_messages = [
            message
            for message in second_messages
            if message.role == "assistant" and message.tool_calls
        ]
        self.assertEqual(len(assistant_tool_messages), 1)
        self.assertEqual(len(assistant_tool_messages[0].tool_calls), 2)
        tool_results = [
            json.loads(message.content)["result"]
            for message in second_messages
            if message.role == "tool"
        ]
        self.assertEqual(tool_results, [5.0, 20.0])

    def test_rejects_tool_call_with_non_dictionary_arguments(self) -> None:
        call = ToolCall("call-1", "calculator", ["not", "a", "dict"])
        agent, client = self.make_agent([LLMResponse(tool_calls=[call])])
        result = agent.run("Vyzkoušej nástroj.")

        self.assertEqual(result.status, "error")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(result.error, "Komunikace s jazykovým modelem selhala.")

    def test_rejects_empty_user_input_without_calling_model(self) -> None:
        agent, client = self.make_agent([])
        result = agent.run("   ")

        self.assertEqual(result.status, "error")
        self.assertEqual(len(client.calls), 0)

    def test_handles_llm_error(self) -> None:
        class FailingClient:
            def chat(self, request):
                raise LLMError("Simulovaná chyba spojení.")

        agent = AIAgent(llm_client=FailingClient(), memory=self.memory)
        result = agent.run("Test spojení")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error, "Komunikace s jazykovým modelem selhala.")

    def test_handles_unexpected_llm_client_exception(self) -> None:
        class BrokenClient:
            def chat(self, request):
                raise RuntimeError("Interní detail, který nemá vidět uživatel.")

        agent = AIAgent(llm_client=BrokenClient(), memory=self.memory)
        result = agent.run("Vyzkoušej neočekávanou chybu.")

        self.assertEqual(result.status, "error")
        self.assertEqual(
            result.error, "Nastala neočekávaná interní chyba LLM klienta."
        )
        self.assertNotIn("Interní detail", result.error)

    def test_rejects_malformed_llm_response(self) -> None:
        class MalformedClient:
            def chat(self, request):
                return {"content": "Toto není LLMResponse."}

        agent = AIAgent(llm_client=MalformedClient(), memory=self.memory)
        result = agent.run("Ověř chybnou odpověď.")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error, "Komunikace s jazykovým modelem selhala.")

    def test_unexpected_tool_exception_does_not_break_agent_loop(self) -> None:
        call = ToolCall("call-1", "calculator", {"operation": "add", "a": 1, "b": 2})
        agent, client = self.make_agent(
            [LLMResponse(tool_calls=[call]), LLMResponse(content="Nástroj selhal bezpečně.")]
        )

        with patch(
            "agent.agent.execute_tool",
            side_effect=RuntimeError("Interní cesta nebo detail"),
        ):
            result = agent.run("Vyzkoušej chybu nástroje.")

        self.assertEqual(result.status, "completed")
        tool_message = next(
            message for message in client.calls[1].messages if message.role == "tool"
        )
        tool_error = json.loads(tool_message.content)
        self.assertIn("error", tool_error)
        self.assertNotIn("Interní cesta", tool_message.content)

    def test_rejects_tool_call_without_valid_id(self) -> None:
        call = ToolCall("", "calculator", {"operation": "add", "a": 1, "b": 2})
        agent, client = self.make_agent([LLMResponse(tool_calls=[call])])
        result = agent.run("Vyzkoušej neplatné ID nástroje.")

        self.assertEqual(result.status, "error")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(result.error, "Komunikace s jazykovým modelem selhala.")

    def test_mock_client_reports_exhausted_responses(self) -> None:
        client = MockLLMClient([])
        with self.assertRaises(LLMError):
            client.chat(LLMRequest(messages=[]))

    def test_reaches_maximum_agent_steps(self) -> None:
        repeated_call = ToolCall(
            "call", "calculator", {"operation": "add", "a": 1, "b": 1}
        )
        agent, client = self.make_agent(
            [LLMResponse(tool_calls=[repeated_call]) for _ in range(MAX_AGENT_STEPS)]
        )
        result = agent.run("Opakovaně počítej 1 + 1.")

        self.assertEqual(result.status, "limit_reached")
        self.assertEqual(result.tool_calls, MAX_AGENT_STEPS)
        self.assertEqual(len(client.calls), MAX_AGENT_STEPS)

    def test_reaches_maximum_tool_calls_even_in_single_batch(self) -> None:
        from config import MAX_TOOL_CALLS

        calls = [
            ToolCall(
                f"call-{index}",
                "calculator",
                {"operation": "add", "a": index, "b": 1},
            )
            for index in range(MAX_TOOL_CALLS + 3)
        ]
        agent, _ = self.make_agent([LLMResponse(tool_calls=calls)])
        with patch("agent.agent.execute_tool", return_value='{"result": 1}') as execute:
            result = agent.run("Proveď mnoho výpočtů.")

        self.assertEqual(result.status, "limit_reached")
        self.assertEqual(result.tool_calls, MAX_TOOL_CALLS)
        self.assertEqual(execute.call_count, MAX_TOOL_CALLS)

    def test_saves_only_user_and_final_assistant_messages(self) -> None:
        agent, _ = self.make_agent([LLMResponse(content="Hotovo.")])
        agent.run("Ulož tuto konverzaci.")

        self.assertEqual(
            self.memory.get_history(),
            [
                {"role": "user", "content": "Ulož tuto konverzaci."},
                {"role": "assistant", "content": "Hotovo."},
            ],
        )

    def test_agent_continues_when_memory_initialization_fails(self) -> None:
        client = MockLLMClient([LLMResponse(content="Odpověď bez paměti.")])
        with patch(
            "agent.agent.AgentMemory",
            side_effect=sqlite3.OperationalError("Databáze není dostupná."),
        ):
            agent = AIAgent(llm_client=client)

        result = agent.run("Odpověz i bez databáze.")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.answer, "Odpověď bez paměti.")
        self.assertIn("Paměť konverzace není dostupná", result.memory_warning)
        self.assertEqual(len(client.calls), 1)

    def test_agent_continues_when_reading_memory_fails(self) -> None:
        class BrokenReadMemory:
            def get_history(self):
                raise sqlite3.OperationalError("Čtení databáze selhalo.")

            def save_exchange(self, user_input, assistant_answer):
                self.saved_exchange = (user_input, assistant_answer)

        memory = BrokenReadMemory()
        client = MockLLMClient([LLMResponse(content="Odpověď bez historie.")])
        agent = AIAgent(llm_client=client, memory=memory)

        result = agent.run("Pokračuj bez historie.")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.answer, "Odpověď bez historie.")
        self.assertIn("Historii konverzace se nepodařilo načíst", result.memory_warning)
        self.assertEqual(
            memory.saved_exchange,
            ("Pokračuj bez historie.", "Odpověď bez historie."),
        )
        self.assertEqual(
            [message.role for message in client.calls[0].messages],
            ["system", "user"],
        )

    def test_agent_preserves_answer_when_saving_memory_fails(self) -> None:
        class BrokenSaveMemory:
            def get_history(self):
                return []

            def save_exchange(self, user_input, assistant_answer):
                raise sqlite3.OperationalError("Zápis do databáze selhal.")

        client = MockLLMClient([LLMResponse(content="Odpověď zůstane zachována.")])
        agent = AIAgent(llm_client=client, memory=BrokenSaveMemory())

        result = agent.run("Ulož mou otázku.")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.answer, "Odpověď zůstane zachována.")
        self.assertIsNone(result.error)
        self.assertIn("nepodařilo se ji uložit", result.memory_warning)

    def test_memory_saves_exchange_atomically(self) -> None:
        with closing(sqlite3.connect(self.memory.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TRIGGER reject_assistant_message
                    BEFORE INSERT ON conversation
                    WHEN NEW.role = 'assistant'
                    BEGIN
                        SELECT RAISE(ABORT, 'Simulované selhání zápisu.');
                    END;
                    """
                )

        with self.assertRaises(sqlite3.IntegrityError):
            self.memory.save_exchange("Uživatelská zpráva", "Odpověď asistenta")

        self.assertEqual(self.memory.get_history(), [])

    def test_to_json_serializes_agent_result(self) -> None:
        serialized = json.loads(
            to_json(AgentResult("completed", "V pořádku", 1))
        )
        self.assertEqual(serialized["status"], "completed")
        self.assertEqual(serialized["tool_calls"], 1)

    def test_missing_llm_client_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AIAgent(llm_client=None, memory=self.memory)


if __name__ == "__main__":
    unittest.main()
