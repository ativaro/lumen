"""One recoverable-removal confirmation for Code collection surfaces."""
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import Qt
from lumen_i18n import tr


def confirm(parent,item):
    if item['archived']:return True
    dialog=QMessageBox(QMessageBox.Question,tr('Lumen · In den Papierkorb'),
        tr('„{0}“ in den Papierkorb verschieben? Du kannst den Eintrag wiederherstellen. Automatische Starts werden gestoppt. Originaldateien, Projektordner und bisherige Ergebnisse bleiben erhalten.',item['title']),
        QMessageBox.Yes|QMessageBox.No,parent)
    dialog.setTextFormat(Qt.PlainText);dialog.setDefaultButton(QMessageBox.No)
    dialog.button(QMessageBox.Yes).setText(tr('In den Papierkorb'));dialog.button(QMessageBox.No).setText(tr('Abbrechen'))
    result=dialog.exec();dialog.deleteLater();return result==QMessageBox.Yes
