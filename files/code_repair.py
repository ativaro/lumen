"""Prepare a user-editable request, without run data, file paths or service grants."""

import json


def request(plan, index):
    nodes = plan["nodes"]
    if type(index) is not int or not 0 <= index < len(nodes):
        raise ValueError("Fehlgeschlagenen Schritt auswählen.")
    safe = [
        dict(
            kind=n["kind"],
            title=n["title"],
            instruction=n["config"][:200] if n["kind"] == "ai" else "",
        )
        for n in nodes
    ]
    return (
        "Prüfe diesen Ablauf und schlage eine korrigierte Fassung zum Testen vor. "
        "Schritt "
        + str(index + 1)
        + " ist fehlgeschlagen. Ursache noch ungeklärt; nicht raten. "
        "Erhalte Aufgabenziel und Bestätigung vor Schreibaktionen. Quellen und Ziele werden "
        "anschließend erneut ausdrücklich gewählt. Keine Rechte erweitern. "
        "Hier nur gekürzte Arbeitsanweisungen, keine Laufdaten. "
        "Ergänze vor dem Absenden bei Bedarf die konkrete Fehlerbeschreibung. Ablauf:\n"
        + json.dumps(safe, ensure_ascii=False)
    )
