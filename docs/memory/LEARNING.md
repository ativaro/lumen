# Persönliches Lernen im Lumen Desktop

Der aktuelle Desktop verwendet den begrenzten `lumen-memory-learning`-Skill und
die zwei internen Werkzeuge `lumen_memory_learning_context` und
`lumen_memory_learn`. `memory_bridge.py` richtet eine getrennte Sitzung über
`memory_agent_config.py` ein; `memory_agent_stdio.py` vermittelt nur die für dieses
Ereignis vorgesehenen Werkzeuge. Es gibt keinen Zugriff auf den gesamten
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

`lumen_memory.py` verwaltet Speicherung, Freigaben, Vergessen und Abruf. Der
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
geprüfte Anbietergrenzen auch hier. Fehler beim Lernen zerstören die eigentliche
Gesprächsantwort nicht und werden nicht blind wiederholt.

## Prüfung und Quellgrenze

Die maßgeblichen Module sind `files/memory_agent.py`, `memory_agent_config.py`,
`memory_agent_stdio.py`, `memory_bridge.py`, `memory_learning.py` und
`lumen_memory.py`. Die Tests `test_memory*` verwenden isolierte Profile und
synthetische Aussagen. Historische Laufzahlen oder Geräteabnahmen sind keine
neue Abnahme einer beliebigen Installation.

[Bedienung](../../WISSEN.md) · [MCP](../../MCP.md) ·
[Desktop-/Server-Zuständigkeit](../desktop-retirement.md)
