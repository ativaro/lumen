# Vorhandene Lumen-Fenster aktivieren

Ein normaler erneuter Start bringt das vorhandene App-Fenster nach vorn, hebt
Minimierung auf und erhält Reiter, maximierte Darstellung und offene Eingaben.
Ein modaler Dialog bleibt der aktive Ansprechpartner. Unter KDE erfolgt die
Aktivierung über den bereits für Vault genutzten KWin-Weg; PID und Lumen-App-ID
begrenzen das Ziel. Liegt das Fenster auf einem anderen virtuellen Desktop,
wechselt KWin dorthin. Andere Desktops verwenden die normale Qt-Aktivierung.

`files/lumen_activation.py` bündelt diesen Weg für Desktop, Suche, System/Sound,
alle nativen Tool-Fenster, Vault-Vorschau sowie Files, Updater und Companion.
Der native C++-Vault verwendet denselben Helfer. Seine Sperr- und Freigabewege
bleiben bestehen; eine Aktivierung entsperrt keinen Tresor und bestätigt nichts.

Files, Updater und Companion reservieren vor der Fensterkonstruktion einen
D-Bus-Dienst. Weitere Starts erreichen das bestehende Fenster, auch während
dessen Aufbau. Tool-Fenster verwenden weiterhin ihre privaten Socket-Endpunkte
und Bibliothekssperren; die Sperre wird jetzt vor der Fensterkonstruktion erworben.
Ein zweiter Start wartet begrenzt auf den ersten, statt zweite Hintergrundjobs
und ein unnötiges Zwischenfenster anzulegen. Backup-Flush bleibt unverändert.

Eine ausdrücklich übergebene Datei oder ein Ordner öffnet sich bei Files in
einem zusätzlichen Reiter; `--select` unterstützt auch lokale Datei-URIs.
Explizite Auftrags-, Bereichs- und Übergabelinks behalten ihre Navigation.
Bewusst neue Gesprächskontexte und einzelne Freigabe-/Aufnahmedialoge behalten
ihre eigenständigen Fenster. Das KDE-Benachrichtigungszentrum bleibt ein Panel.

## Prüfung

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=files python3 -m unittest \
  files.test_lumen_activation files.test_desktop files.test_vault_activation \
  files.test_system_integration files.test_interop_flush files.test_meeting_radio \
  files.test_screen_companion files.test_search_qml files.test_search_launcher \
  files.test_vault_preview
cmake -S native/vault-ui -B native/vault-ui/build
cmake --build native/vault-ui/build --target lumen-vault-lab -j4
bash files/test_activation_kde.sh
```

Die Prozessprüfungen verwenden einen privaten D-Bus und temporäre Daten. Sie
prüfen echte Doppelstarts, keine zweite Fensterkonstruktion, Files-Datei-URI und
Auswahl, einen länger als den IPC-Timeout geöffneten Einstellungsdialog,
Meeting/Radio-Reiter, laufendes Gespräch mit Entwurf und Auftragsnavigation.
Der private KWin-Test prüft Wayland-Fokus, Maximierung, Minimierung, Modalität,
virtuelle Desktops, unterschiedliche Qt-/Desktop-App-IDs, QML und einen echten
zweiten Start des gebauten C++-Vault. Es werden keine Benutzerfenster bedient.

Stand 08.10.2026: 46 gezielte Tests bestehen; C++-Build mit `-Werror` erfolgreich;
privater Wayland-Lauf meldet `LUMEN_KDE_FOCUS_OK`. Unabhängiger statischer Review:
APPROVED nach Behebung und Prozessprüfung des Settings-Timeouts und des
Meeting/Radio-Reiterwechsels. Lokale Protokolle: `/tmp/lumen-activation-focused.log`,
`/tmp/lumen-activation-kde.log`, `/tmp/lumen-activation-cmake.log`.

Quelländerung auf `feature/desktop-workbench`; am 08.10.2026 in die lokale
Benutzerinstallation übernommen (siehe `desktop-workbench-installation.md`).
Die getrennten Gesprächs-/Gedächtnismodule blieben hashgleich erhalten. Bekannte Fehler der vollständigen Ausgangssuite sind
in `desktop-workbench.md` dokumentiert; dieser Änderung liegt gezielte Abdeckung
der betroffenen Einstiegspunkte und der gemeinsamen Aktivierung zugrunde.
