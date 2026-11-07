# tests/test_tools.py

"""Testy nástrojů AI agenta."""

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.tools import calculator, execute_tool, list_files, read_file


class TestCalculator(unittest.TestCase):
    """Testy matematického nástroje."""

    def test_addition(self):
        self.assertEqual(calculator("add", 10, 5), 15.0)

    def test_multiplication(self):
        self.assertEqual(calculator("multiply", 10, 5), 50.0)

    def test_division_by_zero(self):
        with self.assertRaises(ValueError):
            calculator("divide", 10, 0)

    def test_invalid_operation(self):
        with self.assertRaises(ValueError):
            calculator("power", 2, 3)

    def test_invalid_operation_type(self):
        with self.assertRaises(ValueError):
            calculator(["add"], 2, 3)

    def test_boolean_argument_is_rejected(self):
        with self.assertRaises(ValueError):
            calculator("add", True, 5)

    def test_nan_and_infinity_are_rejected(self):
        invalid_values = [math.nan, math.inf, -math.inf]

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    calculator("add", value, 5)


class TestToolExecution(unittest.TestCase):
    """Testy bezpečného vykonávání nástrojů."""

    def test_unknown_tool_is_rejected(self):
        result = execute_tool("unknown_tool", {})
        self.assertIn("error", json.loads(result))

    def test_invalid_tool_name_type_is_rejected(self):
        result = execute_tool(["calculator"], {})
        self.assertIn("error", json.loads(result))

    def test_invalid_arguments_type_is_rejected(self):
        result = execute_tool("calculator", ["add", 2, 3])
        self.assertIn("error", json.loads(result))

    def test_unexpected_tool_exception_is_sanitized(self):
        with patch(
            "agent.tools.AVAILABLE_TOOLS",
            {"broken": lambda: (_ for _ in ()).throw(RuntimeError("tajný detail"))},
        ):
            result = execute_tool("broken", {})

        payload = json.loads(result)
        self.assertIn("error", payload)
        self.assertNotIn("tajný detail", result)


class TestFileAccess(unittest.TestCase):
    """Testy bezpečného přístupu k souborům."""

    def test_read_file(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            test_file = workspace / "test.txt"
            test_file.write_text("Testovací obsah", encoding="utf-8")

            with patch("agent.tools.WORKSPACE_DIR", workspace):
                result = read_file("test.txt")

            self.assertEqual(result, "Testovací obsah")

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()

            with patch("agent.tools.WORKSPACE_DIR", workspace):
                with self.assertRaises(PermissionError):
                    read_file("../secret.txt")

    def test_absolute_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()

            external_file = Path(directory) / "secret.txt"
            external_file.write_text("Tajný obsah", encoding="utf-8")

            with patch("agent.tools.WORKSPACE_DIR", workspace):
                with self.assertRaises(PermissionError):
                    read_file(str(external_file))

    def test_symbolic_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()

            external_file = root / "secret.txt"
            external_file.write_text("Tajný obsah", encoding="utf-8")

            link = workspace / "link.txt"

            try:
                link.symlink_to(external_file)
            except (OSError, NotImplementedError):
                self.skipTest(
                    "Vytváření symbolických odkazů není na tomto systému dostupné."
                )

            with patch("agent.tools.WORKSPACE_DIR", workspace):
                with self.assertRaises(PermissionError):
                    read_file("link.txt")


    def test_list_files_returns_relative_paths_and_truncation_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "b.txt").write_text("B", encoding="utf-8")
            (workspace / "a.txt").write_text("A", encoding="utf-8")

            with (
                patch("agent.tools.WORKSPACE_DIR", workspace),
                patch("agent.tools.MAX_LIST_FILES", 1),
            ):
                result = list_files()

        self.assertEqual(result["files"], ["a.txt"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["max_results"], 1)

    def test_execute_tool_serializes_list_files_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "example.txt").write_text("example", encoding="utf-8")

            with patch("agent.tools.WORKSPACE_DIR", workspace):
                result = execute_tool("list_files", {})

        payload = json.loads(result)
        self.assertEqual(payload["result"]["files"], ["example.txt"])
        self.assertFalse(payload["result"]["truncated"])

    def test_list_files_skips_symbolic_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            external_dir = root / "external"
            external_dir.mkdir()
            (external_dir / "secret.txt").write_text("secret", encoding="utf-8")

            link = workspace / "external-link"
            try:
                link.symlink_to(external_dir, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest(
                    "Vytváření symbolických odkazů není na tomto systému dostupné."
                )

            with patch("agent.tools.WORKSPACE_DIR", workspace):
                result = list_files()

        self.assertEqual(result["files"], [])
        self.assertFalse(result["truncated"])

    def test_read_file_rejects_non_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            folder = workspace / "folder"
            folder.mkdir()

            with patch("agent.tools.WORKSPACE_DIR", workspace):
                with self.assertRaises((ValueError, OSError)):
                    read_file("folder")

    def test_file_size_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            test_file = workspace / "large.txt"
            test_file.write_text("1234567890", encoding="utf-8")

            with (
                patch("agent.tools.WORKSPACE_DIR", workspace),
                patch("agent.tools.MAX_FILE_SIZE", 5),
            ):
                with self.assertRaises(ValueError):
                    read_file("large.txt")


if __name__ == "__main__":
    unittest.main()
