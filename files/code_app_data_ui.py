"""Host-controlled file input and reviewed Notes output; no app-to-host capability."""

import hashlib
import json
from uuid import uuid4
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QComboBox,
    QFileDialog,
    QLineEdit,
    QPlainTextEdit,
)
from tools_ui import label, button
from lumen_i18n import tr
from lumen_jobs import Job


class DataDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.job = None
        self.closed = False
        self.fields = []
        self.pending = False
        self.intent = ("", "")
        self.saved = False
        self.setWindowTitle(tr("Lumen · App-Daten"))
        self.resize(660, 650)
        box = QVBoxLayout(self)
        box.addWidget(label(tr("Mit Lumen-Daten arbeiten"), "codeTitle"))
        box.addWidget(
            label(
                tr(
                    "Nur die gewählte Quelle wird in ein ausdrücklich gewähltes Textfeld deiner App kopiert. Die App erhält keine Lumen-Zugangsdaten und keinen freien Dateizugriff."
                ),
                "codeMuted",
            )
        )
        box.addWidget(label(tr("Textfeld in deiner App")))
        self.target = QComboBox()
        self.target.setAccessibleName(tr("Textfeld in deiner App"))
        box.addWidget(self.target)
        box.addWidget(
            button(tr("Datei auswählen und in App übernehmen"), self.read_file)
        )
        self.status = label("", "codeMuted")
        box.addWidget(self.status)
        box.addWidget(button(tr("App-Ergebnis für Notes prüfen"), self.prepare))
        self.title = QLineEdit(window.item["title"])
        self.title.setMaxLength(200)
        self.title.setAccessibleName(tr("Titel"))
        box.addWidget(label(tr("Titel")))
        box.addWidget(self.title)
        self.body = QPlainTextEdit()
        self.body.setAccessibleName(tr("Notizinhalt"))
        box.addWidget(label(tr("Notizinhalt")))
        box.addWidget(self.body, 1)
        box.addWidget(
            label(
                tr(
                    "Nur den gewünschten Ergebnistext behalten. Bestehende Notizen bleiben unverändert."
                ),
                "codeMuted",
            )
        )
        self.save_button = button(
            tr("Als neue Notiz speichern"), self.save, primary=True
        )
        self.save_button.setEnabled(False)
        box.addWidget(self.save_button)
        box.addWidget(button(tr("Schließen"), self.accept))
        if window.preview:
            window.preview.inspect(self.inspected)

    def inspected(self, value):
        if self.closed or value is None:
            return
        self.fields = [
            f for f in value["fields"] if f["type"] in ("text", "textarea", "search")
        ]
        for f in self.fields:
            self.target.addItem(
                f["name"] or f["id"] or tr("Textfeld") + " " + str(f["index"] + 1), f
            )

    def work(self, fn, done):
        if self.job:
            return
        self.job = Job(fn, self)
        self.setEnabled(False)
        self.job.result.connect(lambda value: None if self.closed else done(value))
        self.job.failed.connect(lambda error: self.status.setText(tr(error)))

        def finished():
            self.job.deleteLater()
            self.job = None
            if not self.closed:
                self.setEnabled(True)

        self.job.finished.connect(finished)
        self.job.start()

    def read_file(self):
        field = self.target.currentData()
        if not field:
            self.status.setText(tr("Bitte ein Textfeld in der App wählen."))
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Lumen · Quelldatei wählen"),
            "",
            tr("Dokumente (*.txt *.md *.csv *.json *.pdf)"),
        )
        if not path:
            return
        from code_blocks_run import read_file

        def read(job):
            value = read_file(path, job)
            if len(value["text"]) > 20000:
                raise ValueError(
                    "Für ein App-Eingabefeld höchstens 20.000 Zeichen verwenden."
                )
            return value

        def loaded(value):
            def copied(observed):
                if self.closed:
                    return
                valid = observed and any(
                    f["id"] == field["id"]
                    and f["name"] == field["name"]
                    and f["index"] == field["index"]
                    and f["value"] == value["text"]
                    for f in observed["fields"]
                )
                self.status.setText(
                    tr("Übernommene Quelle") + ": " + value["filename"]
                    if valid
                    else tr("Die App-Vorschau ist nicht bereit. Bitte erneut prüfen.")
                )

            self.window.preview.inspect(copied, [{**field, "value": value["text"]}])

        self.work(read, loaded)

    def prepare(self):
        def prepared(value):
            if self.closed or value is None:
                return
            self.body.setPlainText(value["text"])
            self.saved = False
            self.save_button.setEnabled(True)

        if self.window.preview:
            self.window.preview.inspect(prepared)

    def save(self):
        title = self.title.text().strip()
        text = self.body.toPlainText()
        if not title or not text.strip() or len(text) > 30000:
            self.status.setText(
                tr("Bitte Titel und höchstens 30.000 Zeichen Notizinhalt eintragen.")
            )
            return
        signature = hashlib.sha256(json.dumps([title, text]).encode()).hexdigest()
        if self.intent[0] != signature:
            self.intent = (signature, uuid4().hex)
        token = self.intent[1]

        def save(job):
            from interop_data import Registry
            from interop_targets import apply

            ref = dict(
                app="code",
                kind="record",
                id=self.window.item["id"],
                title=self.window.item["title"],
            )
            url = Registry().register(ref)
            return apply(
                "wissen.import",
                dict(title=title, text=text, paths=[], source_url=url, source=ref),
                dict(token=token, mode="copy", title=title),
                job,
                store=self.window.collection.store,
            )

        def saved(_):
            self.status.setText(tr("Notiz gespeichert."))
            self.save_button.setEnabled(False)
            self.saved = True

        self.work(save, saved)

    def done(self, result):
        if self.job:
            self.job.cancelled.set()
            if not self.job.wait(2000):
                return
        self.closed = True
        super().done(result)
