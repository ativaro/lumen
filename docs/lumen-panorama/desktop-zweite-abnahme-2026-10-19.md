# Zweite gezielte Desktop-Abnahme · 19.10.2026

Installiert nach Roots Sicht- und Sourceprüfung: Appkatalog und Einrichtung,
Reader/Compose, Hauptgespräch, Audio Studio, Notes, Inbox/Companion sowie
Updater und Arbeitsmodusdialog. Codepin `88d2ae166d131be950c76a9daa43143a8a588a85`.
Die frühere Fein-Fensterdekoration und QML-Suche bleiben erhalten.

Der Appkatalog verwendet den bestehenden AppHeader und zentrale Theme-Radien.
Einrichtung: 24px-Ränder und 26px/500-Titel. Im Hauptgespräch gelten 24/16/224;
der konkrete Sitzungstitel bleibt als Tabtitel17px. Das Speichern-Symbol nutzt
den vorhandenen ButtonText-Mechanismus auch im hellen Theme und deaktiviert.
Gespräch, Entwurf, einmalige Antwort, Schritte und Scrollbedienung bleiben erhalten.
Reader behält Notizen und den Rückweg zur Bibliothek; kompakte Audio-Listen und
Inbox-/Companion-Inhalte bleiben erreichbar. Notes verwendet die freigegebenen
Server-CSS-/Fontressourcen bei unveränderten nativen Schreib- und Rechtewegen.

Genau24 Runtime-Dateien /1.913.668Bytes installiert.618 andere Codeassets und
Vault-Broker hashgleich; keine Sicherheits-/Native-Vault-Freigabe daraus ableiten.
Files `app.py` behält den bereits installierten Mischstand SHA256
`38c5133512f0857ddd577212eebc7508cda446a2cd3df272c5eec42fde4e1933`.
Auch `setup_dialog.py` erhält ausschließlich die abgenommenen UI-Hunks auf seinen
bisherigen Runtime-Stand: unabhängige Diagnose-/Timeoutlogik bleibt unverändert.
Alle anderen Methodenkörper sind AST-gleich zum vorher installierten Setup.
Die sechs Notes-Payloads und die zwei Inbox-/Companion-Payloads entsprechen exakt
ihren Owner-Manifesten; keine TS-Eingangsquellen oder Tests in Runtime kopiert.

48 gezielte Prüfungen gegen den endgültigen Mischkandidaten und48 gegen die
installierten Module bestanden. Enthalten: echte Notes-Web-/Nativewege,
Reader-Rückweg, Audio-Listen, Inbox-Entwurf, Companion-Abbruch/Freigaben,
Gesprächsauswahl/Scrollen/Entwurf und Theme-Kontrast. Eine veraltete Testannahme
„keine Verlaufsnavigation“ wurde auch mit unveränderten installierten Modulen
reproduziert und durch Prüfung vorhandener Einträge/gewählter Gesprächs-ID ersetzt.
Keine Abschwächung des Produktverhaltens. Private HOME-/Lumen-/XDG-Pfade,
separater D-Bus, PID-/Mount-/Netzräume; keine persönlichen Geräte getestet.

12 echte Installed-Bilder (Graphit/Atelier,960×640/1280×800, DE, Skalierung1).
Alle acht Hauptgesprächsbilder sind bytegleich zu Roots abgenommenen Bildern.
Komplette24-Dateien-Installation und Rücknahme auf kleiner Wegwerf-Codekopie
geprüft; diese Kopie nach Abschluss entfernt. Keine App-/KWin-Neustarts,
Nutzerdatenkopien/-migrationen, Pushes oder Server-/Mobile-Deployments.

Belege: `~/.local/state/lumen/panorama-desktop-second-20261019/` mit
`verification.json`, `payload-provenance.json`, `image-manifest.json`,
`installed/receipt.json`, `setup-runtime-ui.diff` und `rollback-selfcheck.json`.
Rückweg: `install-desktop.py rollback [--apply]`. Dieser Rückweg ist vor älteren
Panorama-/Notes-/Main-Rückwegen zu berücksichtigen und verweigert fremde Drift.
Bereits geöffnete Apps übernehmen die Dateien beim normalen Neuöffnen.

Grenzen: System-QML-Token-/EN-Nachtrag ist ein separater, hier nicht installierter
Rest. Keine vollständige KWin-, Hardware- oder Screenreader-Abnahme. Zusätzlich bestanden5 unabhängige Notes-Installed-Prüfungen des Owners;
288/288 installierte Stylewerte stimmen mit der Serverreferenz überein. Belege
unter `~/.local/state/lumen/notes-server-exact-20261019/verification.json`.


## Abgeschlossener System-Nachtrag

Der oben separat gehaltene System-QML-Rest ist anschließend ebenfalls gezielt
installiert: Ownerpin6115a6d, integriert als88aa7f1. Genau `files/system_app.py`,
`files/qml/system/System.qml` und `files/translations/en/core.json`, zusammen
86.595Bytes. Vier gezielte Prüfungen gegen das Runtime-Overlay und dieselben vier
gegen die installierten Module bestanden; keine externe Aktion ausgelöst.
Navigation224px, Rand24px und Titel26px/500 nutzen die vorhandenen Theme-Werte.
Die englische Arbeitsmodus-Beschriftung beschreibt die Einrichtung statt Projekte.

Drei installierte Hashes/Modes und639 unveränderte andere Codeassets sowie
Vault-Broker geprüft. Fünf echte Installed-DE-/EN-Bilder mit synthetischen Werten
aufgenommen und repräsentative System-/Arbeitsmodusansichten visuell geprüft.
Komplette Drei-Dateien-Installation/Rücknahme auf einer privaten kleinen Codekopie
sowie anschließender Live-Rückwegcheck bestanden. Keine weiteren Flächen,
Featurecommits, App-/KWin-Neustarts oder Produktionsgerätetests.

Separater letzter Rückweg und Belege:
`~/.local/state/lumen/system-panorama-tokens-install-20261019/verification.json`,
`installed/receipt.json`, `image-manifest.json`, `rollback-selfcheck.json` und
`install-desktop.py rollback [--apply]`. Diesen Folgeschritt vor der24-Dateien-Runde
zurücknehmen. Die getrennte Drive-404-Arbeit ist nicht Bestandteil dieses Nachtrags.
