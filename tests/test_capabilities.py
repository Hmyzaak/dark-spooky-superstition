"""Testy generování automatického katalogu schopností."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.capabilities import build_capabilities_markdown, write_capabilities_file
from agent.tools import AVAILABLE_TOOLS, TOOL_DEFINITIONS


class TestCapabilitiesCatalog(unittest.TestCase):
    def test_catalog_contains_registered_tools_and_their_schemas(self) -> None:
        content = build_capabilities_markdown()

        for tool_name in AVAILABLE_TOOLS:
            self.assertIn(f"### `{tool_name}`", content)

        for definition in TOOL_DEFINITIONS:
            self.assertIn(definition.description, content)

        self.assertIn('"required"', content)
        self.assertIn("Maximální počet rozhodovacích kroků", content)
        self.assertIn("NEIMPLEMENTOVÁNO", content)

    def test_catalog_does_not_claim_unregistered_tools_as_available(self) -> None:
        with patch("agent.capabilities.AVAILABLE_TOOLS", {"calculator": object()}):
            content = build_capabilities_markdown()

        self.assertIn("### `calculator`", content)
        self.assertNotIn("### `read_file`", content)
        self.assertIn("## Nekonzistence registru", content)
        self.assertIn("`read_file`", content)

    def test_catalog_is_written_to_requested_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "CAPABILITIES.md"
            returned_content = write_capabilities_file(target)

            self.assertTrue(target.is_file())
            self.assertEqual(target.read_text(encoding="utf-8"), returned_content)

    def test_catalog_uses_current_runtime_configuration(self) -> None:
        with patch("agent.capabilities.config.LLM_PROVIDER", "ollama"), patch(
            "agent.capabilities.config.MAX_AGENT_STEPS", 17
        ):
            content = build_capabilities_markdown()

        self.assertIn("Zvolený poskytovatel LLM: `ollama`", content)
        self.assertIn("Maximální počet rozhodovacích kroků: `17`", content)


if __name__ == "__main__":
    unittest.main()
