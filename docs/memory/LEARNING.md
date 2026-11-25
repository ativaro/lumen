# Persönliches Lernen im Lumen Desktop

Der aktuelle Desktop verwendet den begrenzten `lumen-memory-learning`-Skill und
die zwei internen Werkzeuge `lumen_memory_learning_context` und
`lumen_memory_learn`. Der Desktop-Dienst `lumen-service` richtet nach einem Gespräch
eine getrennte Sitzung in einem privaten, kurzlebigen Profil ein
(`native/service/src/learning.rs`); `lumen-service learning-mcp` vermittelt nur die für
dieses Ereignis vorgesehenen Werkzeuge. Es gibt keinen Zugriff auf den gesamten
gewöhnlichen Assistenten-Werkzeugkatalog.

## Freigaben und Übernahme

Gedächtnisnutzung und Lernen müssen ausdrücklich aktiviert sein. Die automatische
Übernahme ist eine weitere Einstellung; andernfalls bleiben Kandidaten zur
Prüfung. Installation, ein erfolgreiches Gespräch oder eine Serververbindung
ändert diese Entscheidungen nicht.

Das Modell kann bis zu drei dauerhafte Fakten, Vorlieben, Entscheidungen oder
bestätigte Lösungen vorschlagen. Jeder Kandidat braucht einen wörtlichen Beleg
aus der aktuellen Nutzeraussage. Zitate, Dokumente und Werkzeugausgaben erteilen
keine Lernfreigabe. Für eine Lösung muss sich die ausdrückliche positive
Bestätigung auf die vorherige abgeschlossene Antwort beziehen. Ein Exitcode,
Höflichkeit oder die eigene Erfolgsaussage des Modells reicht nicht.

Vor Übernahme werden aktuelle Freigaben, Scope, Revisionsstand und bestehende
manuelle Bearbeitungen geprüft. Quellen und bekannte IDs bleiben nachvollziehbar.
Die Modellklassifikation kann falsch sein; der Nutzer kann Vorschläge prüfen,
Erinnerungen bearbeiten oder vergessen. Wiederverwendete Lösungen sind Kontext,
keine Erlaubnis zum Ausführen der damaligen Schritte.

## Lokale Daten und Servergrenze

Der Dienst verwaltet Speicherung, Freigaben, Vergessen und Abruf
(`native/service/src/recall.rs`, Anbindung `files/lumen_memory.py`). Der
lokale Editor wird über die Gedächtniseinstellungen beziehungsweise technisch
`lumen-wissen --area lumen` geöffnet. Der normale Notes-Starter verwendet den
Servereditor und ist davon getrennt.

Projekt-/Ordnerscope beschränkt vorhandenen Kontext; er ist keine globale
Arbeitsraumwahl und keine automatische Freigabe von Serverprojekten. Alte
Zuordnungen bleiben kompatibel. Es wird keine neue Migration, nachträgliche
Freigabe oder vollständige Übernahme alter Notizgeschichten zugesichert.

Der Lernaufruf verwendet das eingerichtete Modell und kann deshalb einen
Cloud-Anbieter erreichen. Lokale Speicherung bedeutet keine ausschließlich
lokale Verarbeitung. Bei aktiviertem Nur-lokal-Modellmodus gelten dessen
geprüfte Anbietergrenzen auch hier: Der Anbieter des Modells muss als lokaler Dienst
mit Loopback-Adresse bestätigt sein, bevor seine Zugangsdaten in das Lernprofil
gelangen. Fehler beim Lernen zerstören die eigentliche
Gesprächsantwort nicht und werden nicht blind wiederholt.

## Prüfung und Quellgrenze

Maßgeblich sind `native/service/src/learning.rs` und `recall.rs` mit ihren Tests
(darunter die aufgezeichneten Antworten der früheren Python-Module); die Tests
`test_memory*` verwenden isolierte Profile und synthetische Aussagen. Historische Laufzahlen oder Geräteabnahmen sind keine
neue Abnahme einer beliebigen Installation.

[Bedienung](../../WISSEN.md) · [MCP](../../MCP.md) ·
[Desktop-/Server-Zuständigkeit](../desktop-retirement.md)
