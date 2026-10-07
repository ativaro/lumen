#!/usr/bin/env python3
"""Render synthetic search states; never reads the user's files or conversations."""
import argparse
import os
from pathlib import Path
import sys
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, default=Path('artifacts/search-qml'))
parser.add_argument('--language', choices=('de', 'en'), default='de')
args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
os.environ['LUMEN_LANGUAGE'] = args.language
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'files'))
from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from search_qml import create_window
from search_controller import SearchController

with tempfile.TemporaryDirectory() as tmp:
    os.environ.update(XDG_CONFIG_HOME=tmp+'/config', LUMEN_DATA=tmp+'/data', LUMEN_TOOLS_DATA=tmp+'/tools')
    app = QGuiApplication([])
    controller = SearchController(tmp, applications=[('Lumen Files', 'lumen-files.desktop'), ('Lumen Wissen', 'lumen-wissen.desktop'), ('Firefox', 'firefox.desktop')])
    engine, window = create_window(app, controller)
    window.show()
    def capture(name):
        QTest.qWait(100)
        image = window.grabWindow()
        assert not image.isNull(), name
        assert image.save(str(args.output/(args.language+'-'+name+'.png')))
    for theme in ('glass', 'graphite', 'atelier', 'midnight'):
        controller.settings.setValue('appearance', theme); controller.settings.sync(); controller.reload_settings()
        capture(theme+'-search')
    controller._conversation = True; controller.stateChanged.emit()
    controller.backend.messages = [dict(info=dict(role='user'), parts=[dict(type='text', text='Wie kann ich meine Reisebilder übersichtlich ordnen?')]),
        dict(info=dict(role='assistant'), parts=[dict(type='text', text='Ich würde mit **Jahr und Reiseziel** beginnen.\n\n1. Bilder nach Aufnahmedatum gruppieren.\n2. Einen Ordner pro Reise anlegen.\n3. Doppelte Aufnahmen vor dem Verschieben prüfen.\n\nSo findest du später auch ohne den genauen Dateinamen schnell zurück.')])]
    controller.update_messages(controller.backend.messages)
    controller.backend.permissions = [dict(id='demo-permission', permission='read', patterns=['~/Bilder/Reisen'])]
    controller.backend.publish_requests()
    for theme in ('glass', 'graphite', 'atelier', 'midnight'):
        controller.settings.setValue('appearance', theme); controller.settings.sync(); controller.reload_settings()
        capture(theme+'-conversation')
    controller.backend.permissions = []
    controller.update_requests([], [dict(id='demo-question', questions=[dict(question='Wie sollen die Ordner heißen?', options=[dict(label='Jahr und Reiseziel', description='2026 · Lissabon'),dict(label='Nur nach Jahr', description='2026')], custom=True)])])
    capture('question')
    controller.update_requests([], [])
    controller.voice.active = True; controller.voice.say_status('listening', 'Mikrofon aktiv · sprich mit Lumen')
    controller.set_voice_level(.65)
    capture('voice')
    window.setWidth(540); window.setHeight(460); capture('compact')
    controller.voice.stop(); controller.shutdown(); window.hide()
    engine.deleteLater(); QTest.qWait(20)
print('Synthetic renders:', args.output)
