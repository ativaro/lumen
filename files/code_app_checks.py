"""Small, explicit form examples. No scripts, selectors or secret fields are stored."""

import json


def cases(value):
    if not isinstance(value, list) or len(value) > 5 or len(json.dumps(value)) > 60000:
        raise ValueError("Höchstens fünf kleine Beispiele speichern.")
    ids = set()
    for case in value:
        if not isinstance(case, dict) or set(case) != {
            "id",
            "name",
            "fields",
            "expect",
        }:
            raise ValueError("Ungültiges Prüfbeispiel.")
        for key, limit in (("id", 80), ("name", 160), ("expect", 2000)):
            if (
                not isinstance(case[key], str)
                or not case[key].strip()
                or len(case[key]) > limit
                or "\0" in case[key]
            ):
                raise ValueError("Ungültiges Beispielfeld: " + key)
        if case["id"] in ids:
            raise ValueError("Doppeltes Prüfbeispiel.")
        ids.add(case["id"])
        fields = case["fields"]
        if not isinstance(fields, list) or len(fields) > 50:
            raise ValueError("Höchstens 50 Beispieleingaben.")
        for f in fields:
            if not isinstance(f, dict) or set(f) != {
                "id",
                "name",
                "type",
                "index",
                "value",
                "checked",
                "selected",
            }:
                raise ValueError("Ungültige Beispieleingabe.")
            if f["type"] not in (
                "text",
                "number",
                "email",
                "url",
                "tel",
                "search",
                "date",
                "time",
                "datetime-local",
                "month",
                "week",
                "range",
                "color",
                "checkbox",
                "radio",
                "textarea",
                "select-one",
                "select-multiple",
            ):
                raise ValueError("Dieses Eingabefeld darf nicht gespeichert werden.")
            if (
                type(f["index"]) is not int
                or not 0 <= f["index"] < 200
                or type(f["checked"]) is not bool
            ):
                raise ValueError("Ungültige Beispieleingabe.")
            for key, limit in (("id", 200), ("name", 200), ("value", 2000)):
                if not isinstance(f[key], str) or len(f[key]) > limit or "\0" in f[key]:
                    raise ValueError("Ungültige Beispieleingabe.")
            if f["selected"] is not None and (
                not isinstance(f["selected"], list)
                or len(f["selected"]) > 50
                or any(
                    not isinstance(s, str) or len(s) > 2000 or "\0" in s
                    for s in f["selected"]
                )
            ):
                raise ValueError("Ungültige Mehrfachauswahl.")
    return value
