# Install and update Lumen Desktop

## Before you begin

Use **Arch Linux or CachyOS, KDE Plasma 6 and a regular user account**. Sign in to a graphical Plasma session. You need internet access for the initial download and any missing packages. Lumen uses your existing desktop session and display manager. Review the [license](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md).

Install Git if your terminal does not recognize the `git` command:

```bash
sudo pacman -S --needed git
```

## One-command installation

From a directory that does not already contain a `lumen` folder, run as your regular user:

```bash
git clone --branch main --single-branch https://github.com/ativaro/lumen.git && bash lumen/bootstrap.sh
```

If you already have the checkout, run `bash bootstrap.sh` from its root. The installer asks for administrator access to install missing dependencies, including CMake, Make, the C++ compiler and the Qt development libraries. It can use an existing Rust toolchain (1.92 or newer) or install Arch's Rust package. The first installation compiles the native components, writes the user bundle under `$XDG_DATA_HOME/lumen` (usually `~/.local/share/lumen`) and then opens the setup wizard.

1. **Choose a language.** English and German are available. The system-language option uses German for German locales and English otherwise.
2. **Set up a model** if you want assistant answers. Select an available provider and model. File browsing, reading and system monitoring are ready independently.
3. **Add speech** if you want dictation or read-aloud. The wizard can prepare local speech recognition and a voice. Dictation language is a separate setting.
4. **Choose your layout.** Activate the Lumen desktop to apply its panels, theme, wallpaper and decorations. Continue without activating it to keep your current layout. Activation saves the previous configuration and reports the backup location.

Start **Lumen** from the application menu. You can return to the wizard through **Settings → Setup**, or run `lumen-setup-wizard`. A user install also provides `~/.local/share/lumen/bin/lumen-setup-wizard`.

## Install the package

For a system-wide Arch package, start in the checkout as a regular user:

```bash
sudo pacman -S --needed base-devel git
./packaging/arch/build-package.sh --install
lumen-setup-wizard
```

The package declares its desktop dependencies, including `plasma-workspace`. Its installer may request administrator authorization. To apply the Lumen layout from a terminal instead of the wizard, use `lumen-desktop-setup --apply --replace-panels` inside the target user's Plasma session. This replaces that user's panels. For the user-only path use bootstrap above.

## Interface language

Select the language in **Settings → Lumen → Interface language**. Reopen applications after the change. Panels pick it up when restarted or at next login. KDE dialogs follow the desktop language. To try one launch in English, use `LUMEN_LANGUAGE=en lumen`.

## AI engine and personal settings

The wizard detects the compatible OpenCode engine and offers available models. Connect an API-key provider in setup, or use the provider's supported OpenCode sign-in flow. Choose a model belonging to an account or local endpoint you can actually use. Seeing a model in the list only confirms that it is listed. Send a short question to test the connection. Provider quotas and charges depend on your account.

Local microphone recognition uses whisper.cpp. Spoken replies and Reader use an installed Piper voice. Transcribed conversation prompts still go to your chosen model. You can install or revisit speech components later in Setup. Files can also enable optional image search, OCR and the document workshop. [Files guide](files/README.md)

## Native updates

Open **Lumen Updater** from the application menu, the topbar or Settings, or run `lumen-updater`. Check for updates, review the selected components, then choose **Update all**. Linux package and Flatpak updates are separate choices. Reopen applications after the update. Plasma panel components may need a fresh login.

Each installation retains its recorded repository. GitHub is the fallback for installations without a recorded source. A system install and a user install with conflicting sources must be updated separately. If the installed updater launcher is missing, use a checkout of **your installation's source** and run `bash bin/lumen-updater` as your desktop user. This opens the updater using the existing desktop runtime.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Git refuses to clone | Check the repository URL and your internet connection. Run `git ls-remote https://github.com/ativaro/lumen.git HEAD` to check whether Git can reach the source. A successful check prints a commit ID and `HEAD`. |
| Setup is missing from the menu | Use the full user-bundle path given above. Confirm that installation completed and you are signed in as the same user. |
| No model replies | Open **Settings → Setup → AI connection**. Check the selected provider, its credentials, the model and the reported connection stage. |
| The model list stays empty or the engine exits | Use **Copy diagnostics** on the connection page. Review it before sharing. It includes versions, the failing stage and status codes. It omits credentials, prompts and raw provider responses. Copying does not upload it. |
| The engine reports an incompatible session database | Lumen checks the existing schema. For the known incompatible layout, the managed engine uses a separate `lumen-v1.db` and preserves the old store. Reconnect credentials if needed. Keep original databases, especially when diagnosing corruption or lock errors. |
| A document is visible but has no selectable text | A scan can display as an image. Use the optional OCR step in the Files document workshop and open the new output in Reader. |
| A window still has the old language or controls | Close and reopen that application. Panel changes can take effect on the next login. |

## Screen companion

Open **Lumen Companion**, select one window, enter a goal and review its preview. Sending a capture needs a vision-capable model. Optional change monitoring waits for stable changes, checks at most once every five seconds and pauses after 30 requests or 20 minutes. If window protection cannot be determined, use manual approval. Minimizing, pausing or closing the companion stops capture. A provider can retain submitted images according to its terms.

## Recover the previous desktop

Activation prints the backup directory under `~/.local/state/lumen/settings-backups/`. Keep that exact path. Log out of Plasma, switch to a text console and run the following with your printed path:

```bash
lumen-desktop-setup --restore /path/to/printed/backup
```

Log in to Plasma again. The restore command refuses to overwrite an active Plasma session.

## Uninstall

For a user installation, run `./uninstall.sh` from its checkout. For the system package, run `lumen-setup --uninstall` as the desktop user and then `sudo pacman -R lumen`. Restore your previous layout separately if desired. Back up personal files and records before changing your installation.

[Guide index](docs/README.md)
