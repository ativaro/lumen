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


class MCPArgumentBoundaryTest(unittest.TestCase):
    """Structured tools pass model-controlled text to fixed programs; none may become an option."""

    def refused(self, tool, arguments):
        with patch.object(mcp, "run", return_value={"rc": 0, "stdout": "", "stderr": ""}) as run:
            tool(arguments)
            run.assert_not_called()

    def test_option_like_and_malformed_values_never_reach_a_program(self):
        cases = (
            (mcp.tool_systemctl, {"action": "status", "unit": "--host=user@example.invalid"}),
            (mcp.tool_systemctl, {"action": "status", "unit": "-H"}),
            (mcp.tool_systemctl, {"action": "is-active", "unit": "a.service b.service"}),
            (mcp.tool_systemctl, {"action": "list-unit-files", "unit": "--root=/tmp"}),
            (mcp.tool_systemctl, {"action": "status", "unit": "a.service", "scope": "--machine=x"}),
            (mcp.tool_journal, {"unit": "--file=/etc/shadow"}),
            (mcp.tool_journal, {"priority": "--directory=/tmp"}),
            (mcp.tool_journal, {"scope": "--root=/"}),
            (mcp.tool_pacman, {"action": "-Qi", "query": "--config=/tmp/pacman.conf"}),
            (mcp.tool_pacman, {"action": "-Ss", "query": "-r"}),
            (mcp.tool_disk, {"path": "--output=source"}),
            (mcp.tool_disk, {"path": "relative"}),
            (mcp.tool_restart_unit, {"unit": "--now.service", "scope": "user"}),
            (mcp.tool_restart_unit, {"unit": "a.service", "scope": "--host=x"}),
            (mcp.tool_restart_unit, {"unit": "a b.service"}),
            (mcp.tool_restart_unit, {"unit": "sddm.service"}),
        )
        for tool, arguments in cases:
            with self.subTest(tool=tool.__name__, arguments=arguments):
                self.refused(tool, arguments)

    def test_valid_values_follow_an_option_terminator(self):
        cases = (
            (mcp.tool_systemctl, {"action": "status", "unit": "sshd.service"}, ["systemctl", "status", "--", "sshd.service"]),
            (mcp.tool_systemctl, {"action": "list-units", "unit": "nvidia*", "scope": "user"},
             ["systemctl", "--user", "list-units", "--no-pager", "--", "nvidia*"]),
            (mcp.tool_systemctl, {"action": "list-unit-files", "unit": "user@.service"},
             ["systemctl", "list-unit-files", "--no-pager", "--", "user@.service"]),
            (mcp.tool_pacman, {"action": "-Ss", "query": "qt6 base"}, ["pacman", "-Ss", "--", "qt6 base"]),
            (mcp.tool_disk, {"path": "/home"}, ["df", "-h", "--", "/home"]),
            (mcp.tool_restart_unit, {"unit": "pipewire.service", "scope": "user"},
             ["systemctl", "--user", "restart", "--", "pipewire.service"]),
            (mcp.tool_notify, {"summary": "--hint=string:x:y", "body": "-t"},
             ["notify-send", "-a", "opencode", "-u", "normal", "--", "--hint=string:x:y", "-t"]),
        )
        for tool, arguments, expected in cases:
            with self.subTest(tool=tool.__name__, arguments=arguments), patch.object(
                    mcp, "run", return_value={"rc": 0, "stdout": "ok", "stderr": ""}) as run:
                tool(arguments)
                self.assertEqual(run.call_args.args[0], expected)

    def test_journal_keeps_validated_unit_and_priority_behind_their_options(self):
        with patch.object(mcp, "run", return_value={"rc": 0, "stdout": "ok", "stderr": ""}) as run:
            mcp.tool_journal({"unit": "sshd.service", "priority": "err..warning", "lines": 5, "scope": "user"})
        argv = run.call_args.args[0]
        self.assertEqual(argv[argv.index("-u") + 1], "sshd.service")
        self.assertEqual(argv[argv.index("-p") + 1], "err..warning")
        self.assertIn("--user", argv)

    def test_screenshots_are_new_png_files_inside_private_or_picture_folders(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as runtime, tempfile.TemporaryDirectory() as outside:
            pictures = Path(home) / "Bilder"; pictures.mkdir()
            located = {"rc": 0, "stdout": str(pictures), "stderr": ""}
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime, "HOME": home}), patch.object(mcp, "run", return_value=located):
                default = Path(mcp.screenshot_target())
                self.assertEqual(default.parent, Path(runtime).resolve() / "lumen-screenshots")
                self.assertEqual(default.parent.stat().st_mode & 0o777, 0o700)
                self.assertEqual(mcp.screenshot_target(str(pictures / "neu.png")), str(pictures.resolve() / "neu.png"))
                existing = pictures / "alt.png"; existing.write_bytes(b"kept")
                link = pictures / "link.png"; link.symlink_to(Path(outside) / "target.png")
                escape = pictures / "ausbruch"; escape.symlink_to(outside)
                for refused in (str(existing), str(link), str(escape / "x.png"), str(Path(outside) / "x.png"),
                                str(Path(home) / ".bashrc"), str(pictures / "x.txt"), "relativ.png", "/etc/cron.d/x.png",
                                str(pictures / "fehlt" / "x.png")):
                    with self.subTest(path=refused), self.assertRaises((ValueError, OSError)):
                        mcp.screenshot_target(refused)
                self.assertEqual(existing.read_bytes(), b"kept")

    def test_refused_screenshot_target_never_starts_a_capture(self):
        with patch.object(mcp, "screenshot_target", side_effect=ValueError("nein")), patch.object(mcp, "run") as run, \
                patch.object(mcp, "lumen_modules") as modules:
            self.assertEqual(mcp.tool_screenshot({"path": "/etc/passwd"}), [{"type": "text", "text": "nein"}])
            run.assert_not_called(); modules.assert_not_called()


if __name__ == "__main__":
    unittest.main()
