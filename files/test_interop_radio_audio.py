import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from tools_data import Library, Cancelled
from tools_radio import radio_result
from interop_radio_audio import audio_source, source_sections, synthesize_radio


class RadioAudioTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.library = Library('radio', self.root)
        (self.root/'de_DE-thorsten-medium.onnx').write_bytes(b'test model')
        self.record = radio_result(json.dumps(dict(sections=[dict(source=0, text='First 🐟 section.\nTwo sentences.'), dict(source=1, text='Second section.')])),
            [dict(title='One', url='https://one.test'), dict(title='Two', url='https://two.test')])

    def job(self, cancel=False, bad_format=False):
        class Job:
            calls = []
            def check(self):
                if cancel and self.calls: raise Cancelled('Abgebrochen')
            def command(inner, args, data=None, **kwargs):
                inner.calls.append((args, data))
                folder = Path(args[args.index('--output-dir')+1])
                for name, frames in (('900', 1500), ('1000', 2250)):
                    with wave.open(str(folder/(name+'.wav')), 'wb') as output:
                        output.setnchannels(1); output.setsampwidth(2)
                        output.setframerate(2000 if bad_format and name == '1000' else 1000)
                        output.writeframes(b'\1\0' * frames)
        return Job()

    def render(self, job):
        with patch('lumen_setup.executable', return_value='test-piper'), patch('lumen_setup.speech_root', return_value=self.root):
            return synthesize_radio(self.record, self.library, job)

    def test_single_model_process_measured_boundaries_and_utf16_sections(self):
        job = self.job()
        result = self.render(job)
        self.assertEqual(len(job.calls), 1)
        lines = job.calls[0][1].decode().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn('🐟', lines[0])
        self.assertEqual(source_sections(self.record), self.record['source_sections'])
        self.assertEqual(result['duration'], 3750)
        self.assertEqual([(row['start'], row['end']) for row in result['audio_source_timeline']], [(0, 1500), (1500, 3750)])
        path = self.library.asset(result['audio'])
        with wave.open(str(path)) as audio: self.assertEqual(audio.getnframes(), 3750)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        record = dict(self.record, **result, audio_hash=hashlib.sha256(self.record['script'].encode()).hexdigest())
        self.assertEqual(audio_source(record, 1499)['url'], 'https://one.test')
        self.assertEqual(audio_source(record, 1500)['url'], 'https://two.test')
        self.assertIsNone(audio_source(record, 3750))
        self.assertIsNone(audio_source(record, 1500, 'edited script'))
        self.assertIsNone(audio_source(dict(record, audio='other.wav'), 1500))
        self.assertEqual(list(self.library.assets.iterdir()), [path])

    def test_failed_or_cancelled_sections_leave_no_partial_audio(self):
        for job, error in ((self.job(cancel=True), Cancelled), (self.job(bad_format=True), ValueError)):
            with self.assertRaises(error): self.render(job)
            self.assertEqual(list(self.library.assets.iterdir()), [])

    def test_edited_or_manual_script_has_no_fabricated_timeline(self):
        self.record['script'] += ' Edited'
        with patch('interop_radio_audio.synthesize', return_value=dict(audio='plain.wav', duration=1000)) as render:
            result = synthesize_radio(self.record, self.library, self.job())
        self.assertEqual(result['audio_source_timeline'], [])
        render.assert_called_once()


if __name__ == '__main__': unittest.main()
