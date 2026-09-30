# Publishing Lumen

Lumen is developed and tested locally but deliberately not published. When you decide
to go public, this is the complete checklist. Nothing here is required for
local use.

## 1. Hosting

- [ ] Create a public repository (GitHub/GitLab/Codeberg).
- [ ] Push the repo:
  ```bash
  git remote add origin https://github.com/ativaro/lumen.git
  git push -u origin master
  ```
- [ ] Update `url=` and `_srcurl` in `packaging/arch/PKGBUILD` to the real repo.
- [ ] Replace `https://github.com/ativaro/lumen.git` placeholders in `README.md`.

## 2. Package source + checksums

The PKGBUILD builds from a local tarball by default (`LOCALSRC=1`) and from the
release URL otherwise. For publishing:

- [ ] Tag a release matching `pkgver`:
  ```bash
  git tag v1.0.0 && git push origin v1.0.0
  ```
- [ ] Fetch the real checksum:
  ```bash
  cd packaging/arch && updpkgsums
  ```
- [ ] Verify a clean build without `LOCALSRC`:
  ```bash
  makepkg -f
  ```

## 3. AUR

- [ ] Generate the AUR tree:
  ```bash
  ./distro/aur/make-aur.sh
  ```
- [ ] Review `distro/aur/.SRCINFO` (generated; not tracked).
- [ ] Push to `ssh://aur@aur.archlinux.org/lumen.git`.
- [ ] Users can then install with `yay -S lumen`.

## 4. Trust / signing

- [ ] Sign packages for a hosted repo:
  ```bash
  ./distro/cachyos/make-repo.sh --sign
  ```
- [ ] Publish the public key and set `SigLevel = Required DatabaseOptional`.

## 5. CI

`.github/workflows/build.yml` already:
- lints shell/python/fish/json,
- builds the package in an Arch container,
- attaches the `.pkg.tar.zst` to a GitHub Release on `v*` tags.

- [ ] Confirm the workflow runs green on the public repo.

## 6. Documentation polish

- [ ] Screenshots / short demo GIF in `README.md`.
- [ ] `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` (optional).
- [ ] Confirm the `LICENSE` (MIT) is correct for you.

## 7. Final sanity

- [ ] Fresh-machine test: install the package on a clean Arch/CachyOS VM and
      confirm the app starts, `lumen-setup` wires opencode, and existing service preferences
      are preserved; new timers remain opt-in.
- [ ] `lumen-setup --uninstall` and `pacman -R lumen` preserve user state and reports.

## Native UI (package revision 14)

The desktop app and Files panel now require `python-pyqt5`, `python-gobject`
and `python-pillow`; the old QML chat and text-file bridge have been removed.
Before publishing, run the native tests:

```bash
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s files -v
```

Also verify the installed launchers, permissions, questions,
image attachments and cancellation on the target OpenCode version. Desktop
context menus and hotkeys must open Lumen without a terminal. Existing services
and OpenCode configuration must retain their settings on upgrade.

Settings smoke check: **Ctrl+,** opens the shared native dialog from both apps.
Read actual panels, shortcut registrations, service states and configured models;
do not change the personal desktop just to test writes. Use isolated QSettings
and mocked native calls for saves, conflicts, service scopes and timer rollback.
Files preferences must affect the current window; startup/appearance preferences
apply to new windows. Saving a Files preference must never enable automatic tool
approval in an existing chat. System editors remain KDE's own dialogs. Background
report options use separate user-systemd drop-ins, not global engine config.

Launcher upgrade check: KDE can retain the old `Exec` of a registered shortcut
after the desktop file and KSycoca cache were updated. In the user's KDE session,
run `/usr/bin/python3 <install>/files/desktop_settings.py refresh-shortcuts`
with `{}` on stdin after replacing desktop files (the user installer does this).
Only Lumen registrations are recreated, retaining custom/disabled keys and a
backup. Invoke the registered Lumen launch and inspect the actual systemd user
unit `ExecStart` and native window; inspecting shortcut key values alone is
insufficient. A panel launcher may hold its own old desktop-file copy: update
the selected widget URL/localPath to `lumen.desktop`, not `opencode.desktop`.
Clipboard explanation defaults to **Meta+Shift+C**; **Meta+Shift+S** belongs to
Spectacle on KDE. Preserve unrelated bindings.

Permission-mode smoke check: default **Nicht mehr nachfragen** off; enable it
while a request is waiting, verify automatic one-time approval for this session
and verified child tasks, then disable it and verify that the next permission
waits. Questions remain manual. Check preference persistence for new windows,
deduplicated replies, errors and cancellation. Proposal tools remain denied;
no global OpenCode configuration is changed.

File-action smoke check: explain/fix/review must show compact result windows (or the Files side panel), without a composer or generated prompts; free chat remains available.

Rename/sort smoke check: select disposable text/PDF/image files in Files, generate
proposals, edit and deselect rows, apply, then undo after reopening the dialog.
Check destination conflicts and changed sources. Proposals must use a fresh
session with all tools denied; only Files performs the confirmed moves. Exercise
repeated dialog open/close while the network backend is active (mouse navigation
uses a GUI-thread event filter, not an application-wide notify override).

Mouse-navigation smoke check: Back/Forward over the file list itself, its viewport,
other child widgets and the gallery; also test XF86Back/Forward browser keys.
Modal dialogs must not navigate the underlying Files window. `FileView.window()`
must remain the inherited Qt method, not an owner reference. Check native window
events as well as directly delivered Qt test events.

Content-search smoke check: use **Inhalte / Ctrl+Shift+F** with disposable text
and multi-page PDFs. Verify literal excerpts and the matching PDF page, optional
synonym expansion, malformed model responses and cancellation while decoding.
Expansion uses an isolated empty directory with project config disabled and all
tools denied; global personal instructions remain active and disclosed. No found
document is attached. Existing local results survive model errors. PDFs need
Poppler's `pdftotext`; scanned images and Office documents are not searched.
