"""Regression checks for the MCP command execution boundary; no commands run."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "lumen_mcp", Path(__file__).resolve().parents[1] / "bin" / "lumen_mcp.py"
)
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)


class MCPCommandTest(unittest.TestCase):
    def test_benign_diagnostics_execute_as_argv_without_a_shell(self):
        commands = (
            ("free -h", ["free", "-h"]),
            ("uptime", ["uptime"]),
            ("systemctl status a.service", ["systemctl", "status", "a.service"]),
            ("journalctl -n 5", ["journalctl", "-n", "5"]),
        )
        for command, required in commands:
            with self.subTest(command=command), patch.object(
                mcp, "run", return_value={"rc": 0, "stdout": "diagnostic result", "stderr": ""}
            ) as run:
                result = mcp.tool_cmd({"command": command})
                run.assert_called_once()
                argv = run.call_args.args[0]
                self.assertIsInstance(argv, list)
                self.assertEqual(argv[0], required[0])
                for argument in required[1:]:
                    self.assertIn(argument, argv)
                self.assertFalse(run.call_args.kwargs.get("shell", False))
                self.assertEqual(result, [{"type": "text", "text": "diagnostic result"}])

    def test_shell_operators_and_substitutions_never_execute(self):
        commands = (
            "free; touch /tmp/pwn",
            "free $(touch /tmp/pwn)",
            "free `touch /tmp/pwn`",
            "free && touch /tmp/pwn",
            "free | touch /tmp/pwn",
            "free > /tmp/pwn",
            "free\ntouch /tmp/pwn",
        )
        for command in commands:
            with self.subTest(command=command), patch.object(
                mcp, "run", return_value={"rc": 0, "stdout": "", "stderr": ""}
            ) as run:
                mcp.tool_cmd({"command": command})
                run.assert_not_called()

    def test_writing_systemctl_git_and_arbitrary_dbus_calls_never_execute(self):
        commands = (
            "systemctl restart sshd.service",
            "systemctl --user enable arbitrary.service",
            "git reset --hard",
            "git config core.sshCommand touch",
            "qdbus6 org.kde.KWin /KWin reconfigure",
            "qdbus6 org.freedesktop.ScreenSaver /ScreenSaver Lock",
        )
        for command in commands:
            with self.subTest(command=command), patch.object(
                mcp, "run", return_value={"rc": 0, "stdout": "", "stderr": ""}
            ) as run:
                mcp.tool_cmd({"command": command})
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
