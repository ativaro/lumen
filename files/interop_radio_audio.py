"""Local speech sections with measured source times, using one speech process."""
import hashlib
import os
from pathlib import Path
import tempfile
import uuid
import wave

from lumen_i18n import tr
from tools_data import synthesize


def source_sections(record):
    script = record.get('script', '')
    if hashlib.sha256(script.encode()).hexdigest() != record.get('edition_script_hash'):
        return []
    sections = record.get('edition_sections', [])
    if not isinstance(sections, list) or not 1 <= len(sections) <= 50:
        return []
    encoded = script.encode('utf-16-le')
    previous, result = 0, []
    for item in sections:
        start, end = item.get('start'), item.get('end')
        if type(start) is not int or type(end) is not int or not previous <= start < end <= len(encoded)//2:
            return []
        try:
            if encoded[previous*2:start*2].decode('utf-16-le').strip(): return []
            text = encoded[start*2:end*2].decode('utf-16-le')
        except UnicodeError: return []
        result.append(dict(title=item.get('title', ''), url=item.get('url', ''), text=text))
        previous = end
    return result if not encoded[previous*2:].decode('utf-16-le').strip() else []


def synthesize_radio(record, library, job):
    """Both speech workers produce one numerically named WAV per input line.

    One model load, one cancellable child, and frame counts rather than estimated
    speaking speed. Edited/manual scripts keep normal speech without guessed links.
    """
    script = record.get('script', '')
    sections = source_sections(record)
    if not sections:
        return dict(synthesize(script, library, job), audio_source_timeline=[], audio_source_hash='', audio_source_asset='')
    if not script.strip() or len(script) > 24000:
        raise ValueError(tr('Das Hörskript muss 1 bis 24.000 Zeichen enthalten.'))
    from lumen_tts import available, command, prepare_text
    if not available():
        raise ValueError(tr('Die lokale Stimme fehlt. Über Einrichtung den Sprachdialog installieren.'))
    name = uuid.uuid4().hex + '.wav'
    output = library.asset(name)
    try:
        with tempfile.TemporaryDirectory(prefix='.radio-speech-', dir=library.assets) as directory:
            # Both workers strip input lines; source paragraph boundaries remain explicit.
            speech = '\n'.join(' '.join(item['text'].splitlines()) for item in sections) + '\n'
            job.command(command(directory, directory=True), data=prepare_text(speech).encode(), timeout=1800)
            parts = list(Path(directory).glob('*.wav'))
            if len(parts) != len(sections) or any(not path.stem.isdecimal() for path in parts):
                raise ValueError(tr('Die lokale Stimme hat keine vollständige Abschnittsfolge erzeugt.'))
            parts.sort(key=lambda path: int(path.stem))
            if sum(path.stat().st_size for path in parts) > 128 * 1024**2:
                raise ValueError(tr('Die erzeugte Radioausgabe ist zu groß. Bitte kürzer vertonen.'))
            job.check()
            with wave.open(str(parts[0]), 'rb') as first:
                params = first.getparams()
                if not first.getnframes() or first.getcomptype() != 'NONE':
                    raise ValueError(tr('Keine Audiodaten erzeugt.'))
            shape = (params.nchannels, params.sampwidth, params.framerate, params.comptype)
            timeline, frames = [], 0
            with output.open('xb') as stream:
                os.fchmod(stream.fileno(), 0o600)
                with wave.open(stream, 'wb') as joined:
                    joined.setparams(params)
                    for index, (path, section) in enumerate(zip(parts, sections)):
                        job.check()
                        with wave.open(str(path), 'rb') as audio:
                            current = (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype())
                            if not audio.getnframes() or current != shape:
                                raise ValueError(tr('Die erzeugten Audioabschnitte haben kein gemeinsames WAV-Format.'))
                            start = round(frames * 1000 / shape[2])
                            copied = 0
                            while data := audio.readframes(65536):
                                job.check(); joined.writeframesraw(data)
                                copied += len(data) // (shape[0] * shape[1])
                            if copied != audio.getnframes():
                                raise ValueError(tr('Ein erzeugter Audioabschnitt ist unvollständig.'))
                            frames += copied
                            timeline.append(dict(start=start, end=round(frames * 1000 / shape[2]), section=index,
                                title=section['title'], url=section['url']))
                stream.flush(); os.fsync(stream.fileno())
            job.check()
        return dict(audio=name, duration=timeline[-1]['end'], audio_source_timeline=timeline,
            audio_source_hash=hashlib.sha256(script.encode()).hexdigest(), audio_source_asset=name)
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def audio_source(record, position, script=None):
    digest = hashlib.sha256((record.get('script', '') if script is None else script).encode()).hexdigest()
    if (type(position) is not int or not record.get('audio') or record.get('audio') != record.get('audio_source_asset')
            or digest != record.get('audio_hash') or digest != record.get('audio_source_hash')
            or digest != record.get('edition_script_hash')):
        return None
    return next((item for item in record.get('audio_source_timeline', []) if item['start'] <= position < item['end']), None)
