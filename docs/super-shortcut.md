# Lumen launch shortcuts

Super/Meta opens the native Lumen Start menu through `lumen-apps.desktop`.
Alt+Space opens Lumen through `lumen-ask.desktop` and the existing `lumen-quick ask`
launcher; Meta+Shift+O remains available. Desktop setup assigns these through
KGlobalAccel, preserves unrelated bindings, and backs up the changed launch actions.
It removes only Lumens obsolete ModifierOnlyShortcuts/Meta entry from kwinrc.
KRunner and the optional toggle no longer own these two keys.

## Optional window toggle

The toggle has no default key. It can be assigned in Lumen System settings.

The dedicated `lumen-toggle.desktop` action calls `lumen-quick toggle`.
A cold launch checks current-user gaming activity before creating a GUI. Warm
launches call `org.lumen.Desktop.Toggle`, which checks the same game detector.
Steam games, active GameMode and Gamescope suppress this shortcut. Notification
quiet-mode preferences do not disable the shortcut protection. Games without
any of these markers are not automatically detected.

Outside gaming, the optional toggle hides a visible Lumen surface and opens the same
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
