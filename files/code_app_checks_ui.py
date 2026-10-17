"""Explicit reusable examples in the existing offline app preview."""

from uuid import uuid4
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QListWidget,
)
from tools_ui import label, button, row
from lumen_i18n import tr
from code_app_checks import cases


class ChecksDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.closed = False
        self.pending = False
        self.example = None
        self.records = window.collection.records
        self.examples = self.records.tests(window.item["id"])
        self.setWindowTitle(tr("Lumen · Prüfbeispiele"))
        self.resize(660, 680)
        box = QVBoxLayout(self)
        box.addWidget(label(tr("Prüfbeispiele"), "codeTitle"))
        box.addWidget(
            label(
                tr(
                    "Speichere bewusst gewählte Beispieleingaben und einen erwarteten Text. Keine Passwörter oder persönlichen Daten verwenden. Der Test nutzt die angezeigte App-Fassung und verändert ihre Eingabefelder."
                ),
                "codeMuted",
            )
        )
        self.name = QLineEdit()
        self.name.setMaxLength(160)
        self.name.setAccessibleName(tr("Name des Beispiels"))
        box.addWidget(label(tr("Name des Beispiels")))
        box.addWidget(self.name)
        self.expect = QLineEdit()
        self.expect.setMaxLength(2000)
        self.expect.setAccessibleName(tr("Erwarteter Text im Ergebnis"))
        box.addWidget(label(tr("Erwarteter Text im Ergebnis")))
        box.addWidget(self.expect)
        self.save_button = button(
            tr("Aktuelle Eingaben als Beispiel speichern"), self.save
        )
        box.addWidget(self.save_button)
        self.list = QListWidget()
        self.list.setAccessibleName(tr("Prüfbeispiele"))
        box.addWidget(self.list)
        self.run_button = button(tr("Beispiel prüfen"), self.run, primary=True)
        self.remove_button = button(tr("Entfernen"), self.remove)
        box.addWidget(row(self.run_button, self.remove_button))
        self.status = label("", "codeMuted")
        box.addWidget(self.status)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setAccessibleName(tr("Tatsächliches Ergebnis"))
        box.addWidget(self.output, 1)
        self.repair = button(tr("Reparatur vorbereiten"), self.prepare_repair)
        self.repair.hide()
        box.addWidget(self.repair)
        box.addWidget(button(tr("Schließen"), self.accept))
        self.refresh()

    def refresh(self):
        self.list.clear()
        self.list.addItems(
            [
                c["name"] + " · " + tr("Erwartet") + ": " + c["expect"]
                for c in self.examples["cases"]
            ]
        )
        self.save_button.setEnabled(len(self.examples["cases"]) < 5)

    def selected(self):
        index = self.list.currentRow()
        if index < 0:
            raise ValueError(tr("Bitte ein Prüfbeispiel auswählen."))
        return self.examples["cases"][index]

    def write(self, value):
        self.examples = self.records.save_tests(
            self.window.item["id"], self.examples["revision"], value
        )
        self.refresh()

    def inspect(self, callback, fields=None):
        if self.pending:
            return
        if not self.window.preview:
            self.status.setText(tr("Bitte warten, bis die App-Vorschau bereit ist."))
            return
        self.pending = True
        self.run_button.setEnabled(False)
        self.save_button.setEnabled(False)

        def done(value):
            if self.closed:
                return
            self.pending = False
            self.run_button.setEnabled(True)
            self.save_button.setEnabled(len(self.examples["cases"]) < 5)
            try:
                if value is None:
                    raise ValueError(
                        tr("Die App-Vorschau ist nicht bereit. Bitte erneut prüfen.")
                    )
                callback(value)
            except (ValueError, OSError) as error:
                self.status.setText(tr(str(error)))

        self.window.preview.inspect(done, fields)

    def save(self):
        name = self.name.text().strip()
        expect = self.expect.text().strip()
        if not name or not expect:
            self.status.setText(tr("Bitte Name und erwarteten Text eintragen."))
            return

        def save(value):
            c = dict(id=uuid4().hex, name=name, expect=expect, fields=value["fields"])
            cases([c])
            self.write(self.examples["cases"] + [c])
            self.name.clear()
            self.expect.clear()
            self.status.setText(tr("Beispiel gespeichert."))

        self.inspect(save)

    def run(self):
        try:
            self.example = self.selected()
        except ValueError as error:
            self.status.setText(str(error))
            return
        example = self.example

        def check(value):
            passed = example["expect"] in value["text"]
            self.output.setPlainText(value["text"])
            self.status.setText(
                tr("Erwartung erfüllt" if passed else "Erwarteter Text fehlt")
            )
            self.repair.setVisible(not passed)

        self.inspect(check, example["fields"])

    def remove(self):
        try:
            example = self.selected()
            self.write([c for c in self.examples["cases"] if c["id"] != example["id"]])
            self.repair.hide()
            self.output.clear()
        except (ValueError, OSError) as error:
            self.status.setText(tr(str(error)))

    def prepare_repair(self):
        if not self.example:
            return
        self.window.request.setPlainText(
            tr("Korrigiere die App, damit das Prüfbeispiel dieses Ergebnis zeigt")
            + ": "
            + self.example["expect"]
        )
        self.window.mode.setCurrentIndex(1)
        self.accept()

    def done(self, result):
        self.closed = True
        super().done(result)
