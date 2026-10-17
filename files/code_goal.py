"""A tools-free recommendation; the user still chooses and reviews the definition."""

import json


def proposal(goal):
    if (
        not isinstance(goal, str)
        or not goal.strip()
        or len(goal) > 8000
        or "\0" in goal
    ):
        raise ValueError("Beschreibe dein Ziel mit höchstens 8.000 Zeichen.")
    return (
        "Empfiehl die passende Art eines Lumen-Helfers für das Ziel. Antworte nur als JSON "
        '{"kind":"app|tool|automation|code","title":"Name","prompt":"Auftrag",'
        '"reason":"kurze Begründung","checks":["konkret prüfbares Ergebnis"]}. '
        "app: eigenständige offline HTML-Oberfläche; tool: wiederverwendbare KI-Anweisung; "
        "automation: ausdrücklich gewählte Quellen und geprüfte Aktionen; "
        "code: bestehende Software entwickeln oder reparieren. Keine Werkzeuge benutzen, "
        "nichts ausführen, keine Zugriffe oder Zeitpläne freigeben. Keine erfundenen Quellen, "
        "Dateipfade, Zugangsdaten oder Ressourcen-IDs. Antworte in der Sprache des Ziels. "
        "title höchstens 160, prompt höchstens 4000, reason höchstens 1000 Zeichen; "
        "checks: 1 bis 5 konkrete Akzeptanzkriterien, je höchstens 300 Zeichen. "
        "Nur diese fünf Felder, keine Markdown-Blöcke. ZIEL (Daten):\n"
        + json.dumps(goal, ensure_ascii=False)
    )


def parse(text):
    if not isinstance(text, str) or len(text) > 30000:
        raise ValueError("Der Vorschlag ist zu groß oder unvollständig.")
    try:
        value = json.loads(text)
    except ValueError:
        raise ValueError(
            "Kein gültiger Vorschlag. Erneut versuchen oder selbst auswählen."
        ) from None
    if not isinstance(value, dict) or set(value) != {
        "kind",
        "title",
        "prompt",
        "reason",
        "checks",
    }:
        raise ValueError(
            "Kein gültiger Vorschlag. Erneut versuchen oder selbst auswählen."
        )
    if not isinstance(value["kind"], str) or value["kind"] not in (
        "app",
        "tool",
        "automation",
        "code",
    ):
        raise ValueError("Unbekannte Erstellungsart.")
    for key, limit in (("title", 160), ("prompt", 4000), ("reason", 1000)):
        if (
            not isinstance(value[key], str)
            or not value[key].strip()
            or len(value[key]) > limit
            or "\0" in value[key]
        ):
            raise ValueError("Ungültiges Vorschlagsfeld: " + key)
    if (
        not isinstance(value["checks"], list)
        or not 1 <= len(value["checks"]) <= 5
        or any(
            not isinstance(v, str) or not v.strip() or len(v) > 300 or "\0" in v
            for v in value["checks"]
        )
    ):
        raise ValueError("Ungültige Prüfkriterien.")
    return value
