"""Offline Qwen speech worker. No sockets, web UI or Qt in the model environment."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import wave


def chunks(text, limit=300):
    """Bound generation length without dropping the rest of a long paragraph."""
    text = text.strip()
    while text:
        end = min(len(text), limit)
        if end < len(text):
            boundaries = list(re.finditer(r'[.!?;:]\s+|\s+', text[:limit+1]))
            if boundaries: end = boundaries[-1].start() or end
        yield text[:end].strip()
        text = text[end:].lstrip()


class Synthesizer:
    def __init__(self):
        # Installation downloads fixed, verified weights; speaking never uses the network.
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        with contextlib.redirect_stdout(sys.stderr):
            import torch
            from qwen_tts import Qwen3TTSModel
            torch.set_num_threads(min(4, os.cpu_count() or 1))
            root = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))) / 'lumen/speech/qwen-0.6b'
            gpu = torch.cuda.is_available()
            self.model = Qwen3TTSModel.from_pretrained(str(root), local_files_only=True,
                device_map='cuda:0' if gpu else 'cpu', dtype=torch.bfloat16 if gpu else torch.float32,
                attn_implementation='sdpa')

    def write(self, text, output, speaker):
        import numpy as np
        if not isinstance(text, str) or not text.strip() or len(text) > 24000:
            raise ValueError('Speech text must contain 1–24,000 characters.')
        output = Path(output)
        # Replace only a complete WAV; interruption never leaves a playable partial result.
        partial = output.with_name(output.name + '.partial')
        partial.touch(mode=0o600)
        try:
            with wave.open(str(partial), 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2)
                previous_rate = None
                for part in chunks(text):
                    with contextlib.redirect_stdout(sys.stderr):
                        audio, rate = self.model.generate_custom_voice(text=part, language='Auto',
                            speaker=speaker, max_new_tokens=2048)
                    samples = np.asarray(audio[0])
                    if not samples.size or not np.isfinite(samples).all():
                        raise ValueError('No usable speech audio generated.')
                    if previous_rate is None: wav.setframerate(rate)
                    elif previous_rate != rate: raise ValueError('Speech sample rate changed.')
                    else: wav.writeframes(b'\0\0' * int(rate * .16))
                    previous_rate = rate
                    wav.writeframes((np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes())
            os.replace(partial, output)
        finally:
            partial.unlink(missing_ok=True)


def main():
    def interrupted(*_): raise InterruptedError('Speech output cancelled.')
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--output'); target.add_argument('--output-dir')
    target.add_argument('--interactive', action='store_true')
    target.add_argument('--check', action='store_true')
    parser.add_argument('--speaker', default='Ryan')
    args = parser.parse_args()
    model = Synthesizer()
    if args.check:
        with tempfile.TemporaryDirectory(prefix='lumen-voice-check-') as directory:
            model.write('Lumen Files ist bereit.', Path(directory)/'check.wav', args.speaker)
        return
    if args.interactive:
        # Owned by a single conversation, kept warm until it ends or is interrupted.
        while line := sys.stdin.readline(200001):
            try:
                if len(line) > 200000: raise ValueError('Speech request too large.')
                request = json.loads(line)
                model.write(request['text'], request['output'], args.speaker)
                print(json.dumps({'ok': True}), flush=True)
            except InterruptedError: raise
            except Exception as error:
                print(json.dumps({'ok': False, 'error': str(error)[-500:]}), flush=True)
    else:
        text = sys.stdin.read(24002)
        if len(text) > 24001: raise ValueError('Speech request too large.')
        if args.output:
            model.write(text.strip(), args.output, args.speaker)
        else:
            for index, line in enumerate(text.splitlines()):
                if line.strip(): model.write(line, Path(args.output_dir)/f'{index:06d}.wav', args.speaker)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(1)
