"""Ruční příkaz pro aktualizaci dokumentace schopností."""

from agent.capabilities import write_capabilities_file


if __name__ == "__main__":
    write_capabilities_file()
    print("Soubor CAPABILITIES.md byl aktualizován.")
