"""Vstupní bod konzolové aplikace AI agenta."""

import logging

from agent.agent import AIAgent
from agent.capabilities import write_capabilities_file
from agent.groq_client import GroqClient
from agent.llm_client import LLMError, OllamaClient
from config import BASE_DIR, LLM_PROVIDER


def create_llm_client():
    """Vytvoří klienta podle proměnné prostředí LLM_PROVIDER."""

    if LLM_PROVIDER == "groq":
        return GroqClient()
    if LLM_PROVIDER == "ollama":
        return OllamaClient()
    raise ValueError(
        f"Neznámý LLM_PROVIDER '{LLM_PROVIDER}'. Použij 'groq' nebo 'ollama'."
    )


def configure_logging() -> None:
    """Ukládá technické chyby do lokálního souboru agent.log."""

    logging.basicConfig(
        filename=BASE_DIR / "agent.log",
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def main() -> None:
    """Spustí interaktivní komunikaci s agentem."""

    configure_logging()

    try:
        # Dokumentace se aktualizuje při každém startu. Agent dostává katalog
        # přímo z aktuální konfigurace a registru, nikoliv ze starého souboru.
        try:
            write_capabilities_file()
        except OSError:
            logging.exception("Nepodařilo se aktualizovat CAPABILITIES.md.")
            print(
                "Upozornění: CAPABILITIES.md se nepodařilo zapsat; agent použije "
                "aktuální katalog přímo z Python konfigurace."
            )
        agent = AIAgent(llm_client=create_llm_client())
    except (ValueError, LLMError) as exc:
        print(f"Nelze spustit agenta: {exc}")
        return

    print("=" * 50)
    print(f"AI AGENT – POSKYTOVATEL: {LLM_PROVIDER.upper()}")
    print("Upozornění: Agent nemá internetové vyhledávání ani externí ověřování faktů.")
    print("U aktuálních nebo nejistých informací si vyžádej důvěryhodný zdroj.")
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
            if result.error_type:
                print(f"Kategorie chyby: {result.error_type}")
            if result.tool_errors:
                print(f"Neúspěšná volání nástrojů: {result.tool_errors}")
            if result.error:
                print(f"Chyba: {result.error}")
            if result.memory_warning:
                print(f"Upozornění paměti: {result.memory_warning}")
        except KeyboardInterrupt:
            print("\nAgent: Ukončuji aplikaci.")
            break


if __name__ == "__main__":
    main()
