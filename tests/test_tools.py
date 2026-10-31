import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.tools import calculator, read_file


class TestCalculator(unittest.TestCase):

    def test_addition(self):
        self.assertEqual(calculator("add", 10, 5), 15)

    def test_multiplication(self):
        self.assertEqual(calculator("multiply", 10, 5), 50)

    def test_division_by_zero(self):
        with self.assertRaises(ValueError):
            calculator("divide", 10, 0)

    def test_invalid_operation(self):
        with self.assertRaises(ValueError):
            calculator("power", 2, 3)


class TestFileAccess(unittest.TestCase):

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


if __name__ == "__main__":
    unittest.main()
