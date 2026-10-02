#!/usr/bin/python3
"""Real multilingual model smoke; synthetic images only, isolated index."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from PIL import Image

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / 'files'))
from photo_tools import available, runtime

if not available(): raise SystemExit('Zuerst die lokale Bildsuche über den Wizard einrichten.')
with tempfile.TemporaryDirectory(prefix='lumen-photo-smoke-') as tmp:
    root = Path(tmp); pictures = root / 'images'; pictures.mkdir()
    for name, color in [('red','red'),('blue','blue'),('yellow','yellow')]:
        Image.new('RGB',(512,512),color).save(pictures / (name + '.png'))
    def search(query):
        result = subprocess.run([str(runtime()/'env-v1/bin/python'), str(repo/'files/photo_tools.py'),
            'search', str(pictures), '--query', query, '--override'],
            env={**os.environ, 'LUMEN_DATA':str(root/'state')}, capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr[-1000:]
        events = [json.loads(line) for line in result.stdout.splitlines()]
        assert events[-1]['done']
        return [e['item'] for e in events if 'item' in e]
    blue = search('Ein vollständig blaues Bild')
    assert Path(blue[0]['path']).name == 'blue.png', blue
    with sqlite3.connect(root/'state/photos.sqlite3') as db:
        before = db.execute('SELECT path,stamp,vector FROM images ORDER BY path').fetchall()
    red = search('Ein vollständig rotes Bild')
    assert Path(red[0]['path']).name == 'red.png', red
    with sqlite3.connect(root/'state/photos.sqlite3') as db:
        assert before == db.execute('SELECT path,stamp,vector FROM images ORDER BY path').fetchall(), 'unchanged images reindexed'
    (pictures/'red.png').unlink()
    remaining = search('Ein rotes Bild')
    assert all(Path(item['path']).name != 'red.png' for item in remaining)
    print('Reale lokale CLIP-Inferenz: deutsche Suchbegriffe, persistente Vektoren und entfernte Dateien geprüft.')
