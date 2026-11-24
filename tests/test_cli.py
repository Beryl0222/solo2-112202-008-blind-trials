"""命令行与机读输出测试。"""
import bootstrap  # noqa: F401  隔离模式路径引导
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CliTest(unittest.TestCase):
    def _run(self, *extra):
        return subprocess.run(
            [sys.executable, "-I", str(ROOT / "run_trials.py"), *extra],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )

    def test_each_command_runs_under_isolated_mode(self):
        for command in ("glossary", "audit", "plan", "adjudicate", "all"):
            result = self._run(command)
            self.assertIn("==", result.stdout)

    def test_json_payload_written(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "out.json"
            result = self._run("all", "--json", str(target))
            self.assertTrue(target.exists())
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(
                set(payload),
                {"glossary", "audits", "plans", "balance", "adjudication"},
            )
            self.assertIn("机读结果已写入", result.stdout)

    def test_repeatable_output(self):
        first = self._run("adjudicate").stdout
        second = self._run("adjudicate").stdout
        self.assertEqual(first, second)

    def test_accepts_explicit_directory_argument(self):
        result = self._run("audit", "--directory", str(ROOT / "materials"))
        self.assertIn("R1", result.stdout)


if __name__ == "__main__":
    unittest.main()
