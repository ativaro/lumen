# Lumen setup

## Objective and acceptance
First launch of Lumen, Files or Search offers a shared, themed native setup wizard.
It can be skipped and reopened from Settings. No terminal is part of the flow.
Existing OpenCode installations and provider configuration are reused. An engine
check lists configured models without sending a prompt or claiming cloud credentials
have been validated. API-key providers can be connected through the OpenCode API.
Optional PDF/media/network/screenshot packages are selected explicitly on Arch/CachyOS.
Offline dictation installs a pinned whisper.cpp build and a checksummed multilingual
model in the user profile. A microphone test uses the existing dictation implementation,
never sends its text, and starts only on a click. Continuous voice dialogue is a
separate feature; this wizard prepares dictation.

## Structure and implementation
Python/PyQt5, current shared palette and widgets. `files/lumen_setup.py` owns setup
checks and the installer worker; `files/setup_dialog.py` owns the wizard. Reuse
`OpenCodeBackend`, `ContextTools`, QSettings and platform package management.
Style follows existing Qt modules: explicit functions, no new framework.

1. Implement and test dependency discovery and verified local speech installation.
2. Build wizard, model/provider controls and shared first-run/settings entry points.
3. Check native UI and real local dictation, document, package and install.

## Verification commands
`QT_QPA_PLATFORM=offscreen PYTHONPATH=files python3 -m unittest files/test_setup.py -v`

`QT_QPA_PLATFORM=offscreen dbus-run-session -- python3 -m unittest discover -s files -v`
(run full suite with isolated HOME/XDG directories).

`./packaging/arch/build-package.sh`

Tests cover failure/integrity paths, preserving existing model files, explicit
installation/auth actions, skip/reopen behavior and dictation through shared code.

## Boundaries
Always show missing/installed/configured states accurately, keep UI responsive,
validate downloads before installing, preserve provider files and existing choices.
Package installation uses native authorization; model downloads require the wizard's
explicit action. Never log keys, publish user data, replace panels or restart Plasma.
UI prerequisites (Python/Qt) must already be installed by the Lumen package/installer.
