# Lumen Super shortcut

The dedicated `lumen-toggle.desktop` shortcut calls `lumen-quick toggle`.
A cold launch checks current-user gaming activity before creating a GUI. Warm
launches call `org.lumen.Desktop.Toggle`, which checks the same game detector.
Steam games, active GameMode and Gamescope suppress this shortcut. Notification
quiet-mode preferences do not disable the shortcut protection. Games without
any of these markers are not automatically detected.

Outside gaming, the shortcut hides a visible Lumen surface and opens the same
conversation again on the next press. It preserves drafts and running work;
a modal confirmation remains visible. Startup requests are coalesced by parity.
An inherited prompt environment variable cannot turn the toggle into a request.
Ordinary launchers and the existing ask shortcut still open Lumen normally.

`test_super_toggle.py` uses an isolated session bus, actual native/QML windows
and a second process to check cold/warm activation, game suppression, drafts,
running work, details and modal dialogs. The installed program can be tested
with `LUMEN_TEST_PROGRAM`. No AI provider or personal profile is used.

A previously running version must be restarted to register the new D-Bus method.
The installer and Arch package include the dedicated desktop shortcut definition;
existing conflicting Plasma mappings require reassignment in keyboard settings.
