"""Ten code versions and five explicit test examples, never automatic runtime snapshots."""

import json
import time
from code_app_checks import cases


class Records:
    def __init__(self, collection):
        self.collection = collection
        self.store = collection.store
        with self.store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS code_app_records (
                entry TEXT NOT NULL, kind TEXT NOT NULL, revision INTEGER NOT NULL,
                value TEXT NOT NULL, created REAL NOT NULL, PRIMARY KEY(entry,kind,revision))""")

    def remember(self, db, item):
        source = item["definition"].get("html", "")
        if not source.strip():
            return
        value = dict(title=item["title"], description=item["description"], html=source)
        db.execute(
            "INSERT OR IGNORE INTO code_app_records VALUES(?,'version',?,?,?)",
            (item["id"], item["revision"], json.dumps(value), time.time()),
        )
        db.execute(
            "DELETE FROM code_app_records WHERE entry=? AND kind='version' AND revision NOT IN (SELECT revision FROM code_app_records WHERE entry=? AND kind='version' ORDER BY revision DESC LIMIT 10)",
            (item["id"], item["id"]),
        )

    def versions(self, identity):
        return self.store.rows(
            "SELECT revision,created FROM code_app_records WHERE entry=? AND kind='version' ORDER BY revision DESC",
            (identity,),
        )

    def version(self, identity, revision):
        rows = self.store.rows(
            "SELECT value FROM code_app_records WHERE entry=? AND kind='version' AND revision=?",
            (identity, revision),
        )
        if not rows:
            raise ValueError("App-Fassung nicht gefunden.")
        from code_app_edit import check

        value = json.loads(rows[0]["value"])
        check(value)
        return value

    def tests(self, identity):
        rows = self.store.rows(
            "SELECT revision,value FROM code_app_records WHERE entry=? AND kind='tests' ORDER BY revision DESC LIMIT 1",
            (identity,),
        )
        return (
            dict(revision=rows[0]["revision"], cases=cases(json.loads(rows[0]["value"])))
            if rows
            else dict(revision=0, cases=[])
        )

    def save_tests(self, identity, revision, value):
        cases(value)
        item = self.collection.get(identity)
        if item["kind"] != "app" or item["archived"]:
            raise ValueError("Die App ist nicht verfügbar oder archiviert.")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT kind,archived FROM code_library WHERE id=?", (identity,)).fetchone()
            if not current or current["kind"] != "app" or current["archived"]:
                raise ValueError("Die App ist nicht verfügbar oder archiviert.")
            row = db.execute(
                "SELECT revision FROM code_app_records WHERE entry=? AND kind='tests' ORDER BY revision DESC LIMIT 1",
                (identity,),
            ).fetchone()
            if (row["revision"] if row else 0) != revision:
                raise ValueError("Prüfbeispiele inzwischen geändert. Bitte neu laden.")
            db.execute(
                "DELETE FROM code_app_records WHERE entry=? AND kind='tests'",
                (identity,),
            )
            db.execute(
                "INSERT INTO code_app_records VALUES(?,'tests',?,?,?)",
                (identity, revision + 1, json.dumps(value), time.time()),
            )
        return dict(revision=revision + 1, cases=value)
