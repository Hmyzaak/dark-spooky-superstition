"""Vstupní bod konzolové aplikace AI agenta."""

from agent.agent import AIAgent
from agent.groq_client import GroqClient
from agent.llm_client import LLMError, OllamaClient
from agent.memory import AgentMemory
from config import LLM_PROVIDER


def create_llm_client():
    """Vytvoří klienta podle proměnné prostředí LLM_PROVIDER."""

    if LLM_PROVIDER == "groq":
        return GroqClient()
    if LLM_PROVIDER == "ollama":
        return OllamaClient()
    raise ValueError(
        f"Neznámý LLM_PROVIDER '{LLM_PROVIDER}'. Použij 'groq' nebo 'ollama'."
    )


def main() -> None:
    """Spustí interaktivní komunikaci s agentem."""

    try:
        agent = AIAgent(llm_client=create_llm_client(), memory=AgentMemory())
    except (ValueError, LLMError) as exc:
        print(f"Nelze spustit agenta: {exc}")
        return

    print("=" * 50)
    print(f"AI AGENT – POSKYTOVATEL: {LLM_PROVIDER.upper()}")
    print("Pro ukončení napiš: exit")
    print("=" * 50)

    while True:
        try:
            user_input = input("\nTy: ").strip()
            if user_input.lower() in {"exit", "quit", "konec"}:
                print("Agent: Na shledanou!")
                break
            if not user_input:
                continue

            result = agent.run(user_input)
            print(f"\nAgent: {result.answer}")
            print(f"Stav: {result.status}")
            print(f"Použité nástroje: {result.tool_calls}")
            if result.error:
                print(f"Chyba: {result.error}")
        except KeyboardInterrupt:
            print("\nAgent: Ukončuji aplikaci.")
            break


if __name__ == "__main__":
    main()
