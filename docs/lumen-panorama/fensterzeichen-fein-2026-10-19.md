# Fensterzeichen Fein

Der Nutzer hat am 19.10.2026 den Entwurf **Fein** freigegeben und den Einbau
beauftragt: dünner Kreis, Lumen-Ausschnitt oben rechts, Winkel auf/zu und Kreuz.
Die drei freigegebenen SVG-Pfade und ihre 1,2 Einheiten Strichstärke sind in den
nativen Aurorae-Zustandsblättern übernommen. Das 24er Raster wird mit 20 logischen
Pixeln in der bestehenden 32×32-Klickfläche dargestellt. Wiederherstellen verwendet
zwei überlagerte Fenster im selben Ring; die native Maximieren-Schaltfläche wechselt
automatisch dorthin. Native Aktionen, Tooltips und Tastaturbedienung bleiben bei KDE.

Alle vier vorhandenen Themes verwenden Text-/gedämpfte Farben der gemeinsamen
Palette. Hover, gedrückt, inaktiv und deaktiviert bleiben erhalten. Schließen zeigt
bei Hover weiter die bestehende Warnfarbe. Es entsteht keine weitere App-Titelleiste.

`lumen_desktop_theme.prepare_decoration` erzeugt `org.lumen.fine.<theme>`. Die neue
Identität vermeidet alte KWin-SVG-Caches; vorhandene Echo-/Originaldateien bleiben als
Rückweg erhalten. `--refresh-decoration` migriert nur ein ausgewähltes älteres
Lumen- oder Echo-Theme unter Sicherung und behält seine Farbvariante. Fremde
Dekorationen werden nicht umgestellt. Die normale Theme-Auswahl erzeugt künftig
Fein. Bereits gestartete Prozesse müssen für spätere Theme-Wechsel regulär neu
geöffnet werden, damit ihr Python-Modul die neue Identität kennt.

Die native KDE-Dekoration gehört zum Desktop-Theme und gilt auch für andere damit
dekorierte KDE-Fenster. Browser und iOS behalten ihre Plattform-Fenstersteuerung;
kein Server- oder Mobile-Release gehört zu diesem reinen Desktop-Schritt.

Prüfung: acht Theme-/Migrations-/Rückwegfälle in privaten Daten-, D-Bus- und
bwrap-Namensräumen; echte Aurorae/KDecoration-Vorschauen aller vier Themes mit
aktiven, inaktiven, maximierten und wiederhergestellten Vorschauzuständen.
Ring-/Pfeil-/Kreuzpfade gegen den freigegebenen SVG-Entwurf geprüft. Die Vorschau
zeigt ihre eigenen zusätzlichen Beispielknöpfe links; die aktive Installation
verwendet unverändert IAX rechts und keine linken Knöpfe. Die native Vorschau
bildet keine vollständige Klickprüfung an einem echten KWin-Fenster ab.

Belege, gesicherte Runtime-Dateien und geprüfter Rückweg:
`~/.local/state/lumen/fine-window-controls-20261019/`. Keine persönlichen Fenster
für Tests geöffnet oder neu gestartet. Keine Datenmigration und kein neuer
Produkt-Arbeitsraum. Die kleine Änderung ersetzt die bisherige Echo-Grafik;
historische Echo-Theme-IDs bleiben ausschließlich als Migrationsquelle erhalten.
