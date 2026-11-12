# Eigener PDF-Kern für Lumen

## Auftrag und Grenze
Der Nutzer verlangt eine eigene Implementierung der PDF-Technik. Kein MuPDF,
PDFium, Poppler, pypdf, ReportLab oder QtPdf als PDF-Backend. Seit dem 12.11.2026
ist der einzige PDF-Kern Lumens Dokument-Kern in Rust (`native/document-core`,
Programm `lumen-document`). Allgemeine Bausteine mit frei nutzbarer Lizenz
(Rasterer, Schrifttabellen, Bilddecoder, Farbverwaltung, Shaping) sind zulässig,
eine fertige PDF-Engine nicht; `check-licenses.py` erzwingt die Lizenzregel.

Dies ist ein vollständiger Ersatzauftrag, kein Versprechen, den gesamten
PDF-Standard sofort abzudecken. Nicht unterstützte Konstrukte müssen mit einem
konkreten Fehler abbrechen; insbesondere keine scheinbar erfolgreichen Exporte
mit verlorenen Inhalten. Der produktive Backend wird erst nach bestandenen
Verhaltensprüfungen umgestellt. Die Umstellung betrifft diese Abhängigkeit; sie ist keine pauschale Lizenzfreigabe für Lumen.

## Aufbau und Reihenfolge
| Bereich | Verantwortung | Datei |
| --- | --- | --- |
| Objekte | Syntax, Querverweise, Objektstreams, Filter, Seitenbaum, Sicherheit | `src/pdf.rs`, `src/security.rs` |
| Text | Schriften, Kodierungen, Wortpositionen, Ebenen, Ersatztext | `src/text.rs`, `src/type1.rs` |
| Zeichnen | Pfade, Bilder, Farbräume, Transparenz, Verläufe, Muster | `src/render.rs`, `src/calculator.rs` |
| Schreiben | Kopieren/Drehen, Schwärzen, OCR-Textschicht, Übersetzungssatz | `src/write.rs`, `src/translate.rs` |

Python bindet den Kern nur noch an: `files/lumen_office.py` (Programm, Fehler,
Helfer), `reader_data.py`, `document_workshop.py`, `translate_pdf.py` und die
Aufrufer von `pdf_tool`. EPUB, HTML und Text bricht weiterhin `lumen_reflow.py`
mit Qt um. Tests: `cargo test` im Kern und `files/test_lumen_pdf*.py`.

## Abnahme
- Eingaben bleiben unverändert; Export überschreibt keine bestehenden Dateien.
- Objekt-/Stream-/Rekursions-/Pixelgrenzen gelten auch bei fehlerhaften PDFs.
- Referenzen aus xref-Tabellen, xref-Streams, Objektstreams und inkrementellen
  Revisionen werden korrekt aufgelöst oder begründet abgelehnt.
- Text/Seitenrotation/Bilder/Vektoren werden mit unabhängigen Testdokumenten
  geprüft; ungeprüfte Funktionen verhindern die produktive Umstellung.
- Schwärzung erzeugt neue Pixel und neue PDF-Objekte; keine Originalstreams,
  Dateianhänge, versteckten Texte oder Metadaten im bereinigten Export.
- Übersetzungen erhalten Bilder, Vektoren und Links; Überlauf bricht atomar ab.
- Gespeicherte Markierungen dürfen durch einen anderen Textumbruch oder andere
  Wortreihenfolge nicht unbemerkt an eine andere Stelle wandern.
- Bestehende PDF-/EPUB-/HTML-/Passwort- und UI-Prüfungen bestehen vor Umstellung.
- Keine Fremd-PDF-Abhängigkeit im endgültigen Laufzeit-/Installationspfad.

## Prüfungen und Arbeitsgrenzen
`cargo test --locked --release` in `native/document-core`, dann
`python3 -m unittest test_lumen_pdf test_lumen_pdf_extended test_lumen_pdf_transparency`
aus files/ im isolierten Profil nach `PUBLISHING.md`, danach gezielte
Reader-/Workshop-/Translate-/Interop-Prüfungen.
Fremde PDF-Programme dürfen ausschließlich als unabhängige Entwicklungsorakel
genutzt werden; sie sind kein Bestandteil des neuen Kerns.
Immer: synthetische Dateien, unveränderte Originale, atomarer Export.
Nie: Nutzerbibliotheken migrieren, solange Ankerkompatibilität ungeprüft ist;
keine eigenen Kryptoprimitiven improvisieren, keine stillen Rendering-Fallbacks.

## Produktiver Umfang (2026-10-05)

Reader, Dokumentenwerkstatt, Layoutübersetzung, Files-Vorschau, Inhaltssuche,
Dokumentenimport und OCR verwenden den eigenen Kern. Setup und Arch-Paket
benötigen keinen fremden PDF-Backend. RustCrypto liefert allgemeine MD5-/SHA-/AES-
Primitiven; RC4, PDF-Schlüsselableitung und Sicherheits-Handler R2–R6 sind eigener Code.

- Syntax, xref-Tabellen/Streams, Objektstreams, inkrementelle Revisionen,
  Seitentree, Flate/LZW/ASCII85/ASCIIHex/RunLength, TIFF-/PNG-Prädiktoren.
- Pfade, Clipping, Text, Form-XObjects, RGB-/Graubilder und JPEG/JPX über allgemeine
  Bilddekodierung, ICC-Bildprofile, CropBox und vier Seitendrehungen.
- Basisfonts über Systemschriften; eingebettete TrueType-/OpenType-Schriften,
  Identity-H/ToUnicode. PDF-Schreiben mit eigenen Objekten und eingebetteten
  statischen TrueType-Schriften; Schrift-Einbettungsrechte werden beachtet.
- Passwortlesen, direkte Inhaltsverzeichnis-Ziele, Link-Anmerkungen und vorhandene
  Anmerkungsdarstellungen. Keine Ausführung von Dokumentaktionen.
- Seitenauswahl, Reihenfolge und Drehung; atomarer Export ohne Überschreiben.
  Jede Schwärzung baut das **gesamte** Ausgabedokument aus neuen Pixeln auf,
  einschließlich unverändert ausgewählter Seiten. Damit bleiben auch in gemeinsam
  genutzten unbenutzten Ressourcen keine entfernten Inhalte zurück. Optionale OCR
  erkennt ausschließlich die bereinigten Pixel; Lumen schreibt die Textschicht.
- Übersetzung erhält Bilder, Vektoren, Link-Ziele und Seitengröße; Text wird passend
  umbrochen/verkleinert. Überlauf oder ungeeignete Schrift verhindern den Export.
  Unbenutzte alte Textstreams werden ebenfalls bereinigt.
- EPUB wird selbst entpackt, OPF/Spine/NCX selbst gelesen; allgemeines QTextDocument
  bricht EPUB/HTML/Markdown/Text um. Netzwerk- und Dateiresourcen werden nicht
  geladen; nur geprüfte Bilder aus dem EPUB-Archiv sind zugelassen.
- Alte Reader-Anker werden additiv migriert: Originalanker bleiben gespeichert;
  nur eindeutige vollständige Zitate erhalten neue Wortindizes und UTF-16-Auswahl.
  Mehrdeutige/Teilwort-/nicht wiedergefundene Stellen bleiben als Notiz erhalten,
  ohne falsche Hervorhebung. Bei geändertem EPUB/Textumbruch zeigt der Reader einen
  Prüfhinweis; alte Seiten-/OCR-Angaben bleiben als Legacy-Daten erhalten.
  Neue Stellenverweise enthalten die Engine-Version. Alte positionsgenaue Links
  öffnen die Seite mit einem Hinweis statt ungeprüft fremde Wortindizes anzuwenden.
- Worker respektieren eigene und geerbte Ressourcenlimits. Files-Suche bleibt
  auf 128 MiB/12 Sekunden und 1 MiB Text pro Datei begrenzt; Volltextimport meldet
  Überschreitung von 120.000 **Zeichen** ausdrücklich, statt UTF-8 zu kürzen.

### Dokument-Kern in Rust als einziger PDF-Kern (seit 12.11.2026)

Reader, Files (Vorschau, Inhaltssuche, Sortiervorschlag), Wissensindex, Texterkennung,
Dokumentenwerkstatt und Layoutübersetzung lesen, zeichnen und schreiben PDFs nur über
`lumen-document`. Der Python-Kern (`files/lumen_pdf*.py`) und jeder Rückfall darauf sind
entfernt; was der Rust-Kern ablehnt, erscheint als übersetzte Meldung.

Vor dem Entfernen wurden beide Kerne an den 78 PDFs des Rechners verglichen: Struktur,
Wörter und Seitenbild gleich auf allen Seiten, die beide lesen; bei der Übersetzung gleiche
Textblöcke in allen 32 Dateien, die beide annehmen. Rust setzt übersetzten Text mit den
Vorschüben der Schrift; bei unverändertem Text liegen die Wörter exakt auf denen des
Originals, Qt wich wegen gerundeter Vorschübe bis 45 Pixel ab. Seitdem neu im Rust-Kern:
ICC-Farbverwaltung (`moxcms`), JPEG 2000 (`hayro-jpeg2000`), Linien mit Muster, radiale
Verläufe zwischen beliebigen Kreisen, graue Transparenzgruppen, Füllen und Umranden als ein
Objekt, Schreiben aus nur besitzergeschützten Quellen, SASLprep für Passwörter der
Revision 6 (`stringprep`) und der Übersetzungssatz (`rustybuzz`, `unicode-linebreak`).

### Bewusste Formatgrenzen

Keine vollständige ISO-32000-Implementierung. Nicht unterstützte Konstrukte
brechen mit einer konkreten Meldung ab, ohne Fallback auf einen anderen PDF-Kern:
Type3, komplexe CMaps/CID-CFF-Zuordnungen, Rechts-nach-links-Text, vertikale
Schriftmetriken, nicht eingebettete CID-Schriften, Ebenenausdrücke (`VE`),
CMYK-Gruppen und nicht separierbare Mischmodi. Ungefärbte Kachelmuster,
Mesh-Verläufe, Inline-Bilder, Text-Clipping und zusätzliche Spezialfilter
(insbesondere CCITT/JBIG2) sind weiterhin offen. Ein JPEG-2000-Bild mit eigenem
Alphakanal (`SMaskInData`) wird ohne diesen Kanal gezeichnet. Radiale Verläufe
zwischen zwei gleich großen Kreisen werden mit 0,1 % kleinerem Startkreis genähert.

Seit dem 11.11.2026 gelesen, mit diesen Grenzen: Knockout-Gruppen (transparente
Objekte darin kosten je drei Flächen aus dem Transparenzbudget; „Alpha als Form“
darin wird abgelehnt), nicht isolierte Gruppen mit äußerer Transparenz (ein
Mischmodus innerhalb wird abgelehnt), gefärbte Kachelmuster bis 4096 px je
Kachel, Ebenen nach der Standardkonfiguration des Dokuments (keine Umschaltung
durch den Leser), symbolische TrueType-Schriften über ihre eigene Zeichentabelle,
nicht eingebettete einfache Schriften über die passende Liberation-Familie mit
den Breiten aus der Datei, ersetzender Markierungstext (`ActualText`) für die
Textauswahl, Linienangaben im Grafikzustand und Flate-Daten, denen nur die
Prüfsumme fehlt. Überdrucken (`OP`, `op`, `OPM`) wird wie am Bildschirm ohne
Überdruckvorschau dargestellt. Das Kopieren von Seiten mit Ebenen bleibt
abgelehnt. Wörter, die nur durch Abstand getrennt sind, werden ab einem Zehntel
der Zeilenhöhe getrennt; dafür trägt der Reader die Kennung `lumen-2` und
verankert Markierungen über ihr Zitat neu. Mehrsprachiger Export setzt eine vollständig passende statische
TrueType-Schrift voraus. Formular-/Signatur-PDFs werden nicht übersetzt; EPUB-DRM
wird nicht verarbeitet. Interne Links auf nicht ausgewählte Exportseiten führen
zu einer Fehlermeldung. Diese Grenzen sind gegenüber dem früheren umfangreicheren
Backend relevant und müssen bei eigenen Dokumenten geprüft werden.

### Verifikation

`cargo test --locked --release` in `native/document-core` und die Python-Tests
`test_lumen_pdf test_lumen_pdf_extended test_lumen_pdf_transparency test_reader
test_workshop test_translate test_interop_reader test_content_search test_studio`
im isolierten Profil nach `PUBLISHING.md`. Die Python-Tests bauen ihre PDFs mit dem
kleinen Testschreiber in `test_pdf_fixtures.py` und prüfen Lesen, Zeichnen und Schreiben
über `lumen-document`.

### Referenzen

- [ISO 32000-1](https://pdfa.org/resource/iso-32000-1/)
- [PDF-Sicherheits-Handler und Errata](https://pdf-issues.pdfa.org/32000-2-2020/clause07.html)
- [RFC 4013 SASLprep](https://www.rfc-editor.org/rfc/rfc4013)

## Historie: Python-Kern (5.10. bis 12.11.2026)

Die folgenden Abschnitte beschreiben Abnahmen des früheren Python-Kerns. Sie sind
Belege, kein aktueller Stand; die Dateien, Pfade und Befehle darin gibt es nicht mehr.

### Lokale Abnahme

95 fokussierte Format-/Workflow-/UI-Tests liefen mit explizit gesperrten Imports
fremder PDF-Engines erfolgreich. Anschließend wurden 47 geänderte/neue Dateien
in der vorhandenen Benutzerinstallation übernommen und byteweise verglichen.
Die vorherigen Programmdateien sind unter
`~/.local/share/lumen-backups/pdf-engine-20261005-231625/` gesichert; Nutzerdaten
wurden dabei nicht geändert. Ein isoliertes Profil bestätigte am installierten
Starter PDF-Kalt-/Warmstart, Reader-Seitendarstellung, Übersetzung und
Dokumentenwerkstatt-Export, ebenfalls mit gesperrten fremden PDF-Modulen.

Die bestehende systemweite Entwicklerinstallation fremder PDF-Werkzeuge wurde
nicht deinstalliert: Sie ist keine Lumen-Abhängigkeit und könnte anderen
Programmen dienen. Lumen installiert oder importiert diese Werkzeuge nicht.
Zwei separate Setup-Providertests scheitern identisch im unveränderten
Ausgangsstand; die PDF-Setup-Prüfung und übrigen Setup-Tests bestehen.

### Workshop-PDF und Erweiterungen (2026-10-06)

Der gemeldete Workshop in Downloads liegt zweimal identisch vor (92 Seiten).
Die Originale bleiben unverändert; keine Inhalte daraus werden als Testfixture
eingecheckt. Die Datei deckt mehrere zuvor abgelehnte Konstrukte auf:

- Leere indirekte Verweise (hier das Inhaltsverzeichnis) ergeben gemäß
  ISO 32000-1 7.3.10 `null`; erforderliche Seiten-/Streamstrukturen werden
  weiterhin geprüft. Eine eng begrenzte Nullzahl-Reparatur behandelt den
  tatsächlich vorkommenden fehlerhaften Zahlenwert des Präsentationsexporters.
- RGB-/Gray-Seitengruppen, isolierte Form-Gruppen, Füll-/Konturdeckkraft,
  separierbare Mischmodi und Alpha-/Luminosity-Weichmasken. Masken behalten die
  beim `gs` gesetzte Matrix. Gruppendeckkraft wird nach der inneren Überlagerung
  angewendet. Temporäre Flächen entstehen erst in der angeforderten Auflösung;
  Pixel- und Rekursionsgrenzen gelten auch für verschachtelte Effekte.
- Axiale und eingeschlossene radiale Verläufe, Shading-Muster mit eigener
  Matrix, Fortsetzungsgrenzen und Muster-Hintergrundfarbe.
- Gedrehte/gespiegelte Texte, dazu passende Wortrechtecke und gedrehte
  Übersetzungsblöcke. Seitenkopien erhalten Gruppen und Seiteneinheiten;
  Zahlen werden ohne die bisherige Rundung auf acht Nachkommastellen geschrieben.
- Benannte Ziele (alter Dictionary- und neuer Namenbaum), Bildmasken,
  Farbschlüssel, 1/2/4/8/16-Bit-Bilddaten, Decode-Bereiche, Indexed/Cal/Lab/
  ICC/Separation/DeviceN-Farbräume sowie Funktionen 0/2/3/4.

Alle 92 Seiten wurden gerendert und mit einem unabhängigen Entwicklungsrenderer
verglichen. Nach eigenem Seitenexport stimmen Text, Wortrechtecke und gerenderte
Pixel aller 92 Seiten mit dem eigenen Original-Rendering überein. Zusätzlich
geprüft: Reader-Metadaten, Suche, native Reader-/Files-Vorschau, Drehung und
dauerhafte Schwärzung; die SHA-256-Prüfsumme des Originals bleibt gleich.
Die synthetischen Tests benötigen keine fremde PDF-Engine; die ursprüngliche
Datei und die Vergleichswerkzeuge sind keine Projektabhängigkeit.

67 fokussierte Prüfungen bestehen mit gesperrten Fremd-PDF-Imports. Auch der
installierte Reader und die Files-Vorschau wurden mit der Originaldatei in einem
isolierten Profil geprüft, einschließlich dieser Importsperre in Workerprozessen.
Die Programm-Rückfallkopie liegt unter
`~/.local/share/lumen-backups/pdf-workshop-20261006-000757/`. Ein zwischenzeitliches
Update auf `7818b8f` hatte ältere PDF-Aufrufer zurückgebracht; sie sind gezielt
wiederhergestellt, ohne die neuen Echo-Fensterdekorationen zu überschreiben.

Diese Abnahme bestätigt den Workshop und die genannten Konstrukte. Die oben
aufgeführten weiteren Formatlücken bleiben offen; vollständige PDF-Parität ist
damit ausdrücklich noch nicht erreicht.
