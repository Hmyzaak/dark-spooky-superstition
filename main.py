from agent.agent import AIAgent


def main() -> None:
    """Spustí interaktivní komunikaci s agentem."""

    agent = AIAgent()

    print("=" * 50)
    print("AI AGENT – PRVNÍ VERZE")
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
    