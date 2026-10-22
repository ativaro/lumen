# Lumen Anwendungsmenü

Die vorhandene linke Desktop-Insel zeigt bei maximierten Fenstern den Appnamen
und die tatsächlich von der aktiven App angebotenen Menüs. Bei normalen Fenstern
oder zu wenig Platz bleibt ein kompakter Menüknopf erreichbar. Im echten Vollbild
werden die Menü-Applets ausgeblendet. Apps ohne Menüaktionen erhalten keine
erfundenen Einträge.

Die Darstellung folgt den vorhandenen Inseln und ihrer Panorama-Palette;
Systemschrift, Tastaturbedienung, deaktivierte Aktionen und Monitorzuordnung
werden von Qt/KDE übernommen. Die Panorama-Referenz enthält keine eigene
KDE-Systemleiste: Hier gelten deshalb die bestehenden Inselmaße und die
gemeinsamen Theme-Farben.

## Aufbau

- `plasmoid/appmenu/` enthält die einzige QML-Implementierung.
- `native/appmenu/factory.cpp` instanziiert den installierten KDE-AppMenu-Backend.
  Ein kleiner Factory-Adapter ist notwendig, weil `X-Plasma-RootPath` unter
  Plasma 6.8 zusätzlich KDEs eingebettete QML-Oberfläche erzwingt.
  Er gibt ausschließlich den zugehörigen nativen Untermenüs die Palette des
  vorhandenen Plasma-Themes; das globale KDE-Farbschema wird nicht verändert.
- Pro Insel werden zwei verwaltete Instanzen derselben Implementierung angelegt:
  eine feste Leistenansicht und eine feste kompakte Ansicht. Nur die passende
  Instanz ist sichtbar. So werden die nativen `QMenu`-Eigentumsverhältnisse beim
  Maximieren nicht zwischen Präsentationsarten umgebaut.
- `WindowMenuState.qml` beobachtet die aktiven Fenster über KDEs Taskmodell,
  beschränkt auf den jeweiligen Bildschirm. Geöffnete Menüs behalten ihr Fenster.
- `desktop/appmenu.js` ergänzt vorhandene Inseln, erhält andere Applet-IDs und
  begrenzt die Erweiterung durch den Abstand zur Suchinsel. Wiederholtes Ausführen
  erzeugt keine weiteren Instanzen. Die ursprüngliche sichtbare Inselbreite bleibt
  gespeichert, weil Plasma bei inhaltsangepassten Inseln eine bildschirmbreite
  Mindestlänge melden kann. Ohne installierten Menü-Baustein bleibt der
  bisherige Desktop nutzbar.
- `desktop/layout.js` verwendet denselben Helfer auch für neue Desktop-Layouts.

## Installation und Rückweg

Voraussetzung: Plasma/Plasma Workspace 6.8 oder neuer. Das Arch-Paket baut den
Adapter mit `native/build-appmenu.sh` und installiert ihn unter
`/usr/lib/qt6/plugins/plasma/applets/`, das QML-Paket unter
`/usr/share/plasma/plasmoids/org.lumen.appmenu/`.

Der allgemeine benutzerlokale `install.sh` installiert diesen optionalen nativen
Zusatz nicht automatisch. Eine gezielte Installation muss das Add-on, den
Layout-Helfer und die passende Desktop-Setup-Anbindung gemeinsam bereitstellen.
Bestehende Inseln werden über `installLumenAppMenus(panels())` ergänzt; dafür
ist kein vollständiger Desktop-Neuaufbau nötig.

Vor der Aktivierung Panelgeometrie, Applet-IDs, Dateien und Hashes sichern.
Ein Rückweg entfernt nur die neu erzeugten Menü-IDs und stellt die gespeicherten
Panelmaße sowie die gezielt veränderten Dateien wieder her. Die bisherigen
Leisten-Applets müssen dafür nicht ersetzt werden.

## Prüfung

`plasmoid/tests/tst_windowmenu.qml` prüft Fensterwechsel, Maximieren, Vollbild,
Menüverlust und Fokusbindung. `files/test_appmenu_layout.py` prüft bestehende
Inseln, Wiederholbarkeit, knappen Platz und fehlende optionale Komponenten.
Die grafische Abnahme muss echte App-Menüs, beide Bildschirme und alle vier
Themes einschließlich der kompakten Bedienung prüfen; reine Modelltests reichen
nicht aus.

KDE-Referenzen: [AppMenu-Backend](https://github.com/KDE/plasma-workspace/tree/Plasma/6.8/applets/appmenu),
[Applet-Laden](https://github.com/KDE/libplasma/blob/Plasma/6.8/src/plasma/pluginloader.cpp).
