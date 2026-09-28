# Publishing Lumen

Lumen is developed and tested locally but deliberately not published. When you decide
to go public, this is the complete checklist. Nothing here is required for
local use.

## 1. Hosting

- [ ] Create a public repository (GitHub/GitLab/Codeberg).
- [ ] Push the repo:
  ```bash
  git remote add origin <repo-url>
  git push -u origin master
  ```
- [ ] Update `url=` and `_srcurl` in `packaging/arch/PKGBUILD` to the real repo.
- [ ] Replace `<repo-url>` placeholders in `README.md`.

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
- [ ] Push to `ssh://aur@aur.archlinux.org/opencode-lumen.git`.
- [ ] Users can then install with `yay -S opencode-lumen`.

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
      confirm the app starts, `lumen-setup` wires opencode, and the services
      are active (`systemctl status lumen-agentd lumen-watch.timer`).
- [ ] `lumen-setup --uninstall` and `pacman -R opencode-lumen` leave no residue.

## Native UI (package revision 10)

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

File-action smoke check: explain/fix/review must show compact result windows (or the Files side panel), without a composer or generated prompts; free chat remains available.
