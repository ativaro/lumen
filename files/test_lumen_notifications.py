import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lumen_notifications import change, publish, snapshot


class NotificationTest(unittest.TestCase):
    def test_notes_name_preserves_existing_notification_identity_and_mute(self):
        from lumen_notifications import database, set_preference

        with tempfile.TemporaryDirectory() as directory, patch("lumen_notifications.toast"):
            path = Path(directory) / "notifications.sqlite3"
            first = publish("Lumen Wissen", "sync", "Synthetic notice", path=path)
            self.assertEqual(snapshot(path=path, wake=False)["items"][0]["source"], "Lumen Notes")
            second = publish("Lumen Wissen", "sync", "Synthetic notice", revision=2, path=path)
            self.assertEqual(first, second)
            set_preference("Lumen Wissen", "muted", path=path)
            self.assertEqual(snapshot(path=path, wake=False)["items"], [])
            with database(path) as db:
                self.assertEqual(db.execute("SELECT source FROM notifications").fetchone()["source"], "Lumen Wissen")

    def test_game_context_and_restoration_receipt_precedes_tray_change(self):
        import json
        import subprocess
        from types import SimpleNamespace

        from lumen_notifications import configure_popups, popup_context

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("PySide6.QtCore.QSettings") as settings,
        ):
            settings.return_value.value.side_effect = lambda key, default, **kwargs: (
                default
            )
            with patch("lumen_hardware.activity", return_value=["Steam-Spiel"]):
                self.assertTrue(popup_context()["gaming"])
            with patch("lumen_hardware.activity", return_value=["OBS geöffnet"]):
                self.assertFalse(popup_context()["gaming"])
            path = Path(directory) / "notifications.sqlite3"

            def execute(*args, **kwargs):
                if "filter(w=>items(w)" in args[0][-1]:
                    return SimpleNamespace(stdout="[12,34]")
                self.assertEqual(
                    json.loads(path.with_name("notification-trays.json").read_text()),
                    [12, 34],
                )
                raise subprocess.CalledProcessError(1, args[0])

            with (
                patch("lumen_notifications.location", return_value=path),
                patch("lumen_notifications.subprocess.run", side_effect=execute),
                self.assertRaises(subprocess.CalledProcessError),
            ):
                configure_popups(True)
            settings.return_value.setValue.assert_not_called()

    def test_retention_starts_at_archive_and_preserves_pending_server_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notifications.sqlite3"
            with patch("lumen_notifications.time.time", return_value=1000):
                identity = publish("Lumen", "old", "Result", popup=False, path=path)
            with patch("lumen_notifications.time.time", return_value=4000000):
                change(identity, "archive", path)
                self.assertEqual(len(snapshot(path)["items"]), 1)
            with patch("lumen_notifications.time.time", return_value=7000000):
                self.assertEqual(snapshot(path)["items"], [])

    def test_reminder_survives_restart_and_only_wakes_once(self):
        from lumen_notifications import remind

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("lumen_notifications.time.time", return_value=1000),
        ):
            path = Path(directory) / "notifications.sqlite3"
            one = remind("Prüfen", "1970-01-01T00:30:00+00:00", "reminder", path)
            self.assertEqual(
                one, remind("Prüfen", "1970-01-01T00:30:00+00:00", "reminder", path)
            )
            with self.assertRaises(ValueError):
                remind("Prüfen", "1970-01-01T00:30:00", "bad", path)
            with self.assertRaises(ValueError):
                remind(
                    "Andere Erinnerung", "1970-01-01T00:30:00+00:00", "reminder", path
                )
            self.assertEqual(snapshot(path)["unread"], 0)
            with (
                patch("lumen_notifications.time.time", return_value=1900),
                patch("lumen_notifications.toast") as toast,
            ):
                self.assertEqual(snapshot(path)["unread"], 1)
                snapshot(path)
                self.assertEqual(toast.call_count, 1)

    def test_replay_revision_account_isolation_and_dismissal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notifications.sqlite3"

            def send(**kwargs):
                return publish(
                    "Lumen Projekte",
                    "run-1",
                    "Ergebnis",
                    popup=False,
                    path=path,
                    **kwargs,
                )

            identity = send()
            self.assertEqual(send(), identity)
            change(identity, "read", path)
            send()
            self.assertEqual(snapshot(path)["unread"], 0)
            send(revision=2)
            self.assertEqual(snapshot(path)["unread"], 1)
            send(revision=1)
            self.assertEqual(snapshot(path)["items"][0]["revision"], 2)
            change(identity, "later", path)
            self.assertEqual(snapshot(path)["unread"], 0)
            change(identity, "now", path)
            change(identity, "archive", path)
            self.assertTrue(snapshot(path)["items"][0]["archived"])
            second = send(scope="server:other-user")
            self.assertNotEqual(second, identity)
            self.assertEqual(
                len(snapshot(path)["items"]), 1
            )  # Unattached accounts are not visible.
            with self.assertRaises(ValueError):
                change(identity + ";id", "open", path)
            with self.assertRaises(ValueError):
                change(identity, "shell", path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with sqlite3.connect(path) as db:
                self.assertEqual(
                    db.execute("SELECT count(*) FROM notifications").fetchone()[0], 2
                )

    def test_popup_failure_keeps_durable_card(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notifications.sqlite3"
            with patch("lumen_notifications.subprocess.run", side_effect=OSError):
                publish("Lumen", "one", "Private title", "Private body", path=path)
            self.assertEqual(snapshot(path)["unread"], 1)

    def test_server_roundtrip_offline_replay_and_revocation(self):
        from datetime import datetime, timezone

        from notification_sync import synchronize

        config = {"server": "https://server.test", "device_id": "device"}
        profile = {
            "notification_protocol": 1,
            "user_id": "00000000-0000-0000-0000-000000000001",
            "capabilities": ["notifications"],
        }
        remote = {
            "id": 1,
            "title": "Server result",
            "body": "",
            "task_id": None,
            "created": datetime.now(timezone.utc).isoformat(),
            "read": False,
            "archived": False,
            "snoozed_until": None,
            "state_revision": 1,
        }
        calls = []
        in_flight_click = []

        def request(config, url, body=None):
            calls.append(url)
            if body:
                if in_flight_click:
                    change(in_flight_click.pop(), "archive", path)
                self.assertEqual(body["revision"], remote["state_revision"])
                remote.update({k: v for k, v in body.items() if k != "revision"})
                remote["state_revision"] += 1
                return dict(remote)
            return {"items": [dict(remote)], "next": None}

        with (
            tempfile.TemporaryDirectory() as directory,
            patch("lumen_connect.read_config", return_value=config),
            patch("lumen_notifications.subprocess.run") as popup,
        ):
            path = Path(directory) / "notifications.sqlite3"
            synchronize(config, profile, request, path)
            self.assertEqual(popup.call_count, 1)
            identity = snapshot(path)["items"][0]["id"]
            change(identity, "read", path)
            self.assertEqual(snapshot(path)["unread"], 0)
            synchronize(config, profile, request, path)
            self.assertTrue(remote["read"])
            synchronize(config, profile, request, path)
            self.assertEqual(popup.call_count, 1)
            self.assertEqual(sum(url == "/bridge/notifications/1" for url in calls), 1)
            change(identity, "unread", path)
            in_flight_click.append(identity)
            synchronize(config, profile, request, path)
            self.assertTrue(snapshot(path)["items"][0]["archived"])
            synchronize(config, profile, request, path)
            self.assertTrue(remote["archived"])
            synchronize(config, {**profile, "capabilities": []}, request, path)
            self.assertEqual(snapshot(path)["items"], [])
            with self.assertRaises(ValueError):
                change(identity, "open", path)


if __name__ == "__main__":
    unittest.main()
