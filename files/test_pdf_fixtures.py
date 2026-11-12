"""Small PDF test documents built from explicit format operators, and the document core's view of them.

The writer here only assembles objects for tests; reading, drawing and writing PDFs is the document core's job."""
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import zlib


class Name(str):
    pass


class Ref(int):
    @property
    def number(self): return int(self)


class Stream:
    def __init__(self, attrs, raw): self.attrs, self.raw = attrs, raw


def serialize(value):
    if value is None: return b'null'
    if value is True or value is False: return b'true' if value else b'false'
    if isinstance(value, Ref): return b'%d 0 R' % value
    if isinstance(value, int): return str(value).encode()
    if isinstance(value, float):
        assert math.isfinite(value)
        return (f'{value:.6f}'.rstrip('0').rstrip('.') or '0').encode()
    if isinstance(value, Name): return b'/' + b''.join(bytes([c]) if 33 < c < 127 and c not in b'()<>[]{}/%#' else b'#%02x' % c for c in value.encode())
    if isinstance(value, (bytes, bytearray)): return b'(' + bytes(value).replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)').replace(b'\r', b'\\r') + b')'
    if isinstance(value, str): return serialize(value.encode())
    if isinstance(value, (list, tuple)): return b'[' + b' '.join(serialize(v) for v in value) + b']'
    if isinstance(value, dict): return b'<<' + b''.join(serialize(Name(k)) + b' ' + serialize(v) + b' ' for k, v in value.items()) + b'>>'
    if isinstance(value, Stream):
        return serialize(dict(value.attrs, Length=len(value.raw))) + b'\nstream\n' + value.raw + b'\nendstream'
    raise TypeError(type(value))


class Writer:
    """Objects in order; the catalog is object 1 and the page tree object 2."""
    def __init__(self):
        self.objects = [{'Type': Name('Catalog'), 'Pages': Ref(2)}, None]
        self.root, self.tree, self.page_refs = Ref(1), Ref(2), []

    def add(self, value):
        self.objects.append(value); return Ref(len(self.objects))

    def stream(self, data, **attrs):
        return self.add(Stream(attrs, bytes(data)))

    def add_page(self, width, height, content=b'', resources=None):
        page = {'Type': Name('Page'), 'Parent': self.tree, 'MediaBox': [0, 0, width, height],
                'Resources': resources if resources is not None else {}, 'Contents': self.stream(content)}
        self.page_refs.append(self.add(page)); return page

    def bytes(self):
        self.objects[1] = {'Type': Name('Pages'), 'Kids': list(self.page_refs), 'Count': len(self.page_refs)}
        out = bytearray(b'%PDF-1.7\n'); offsets = []
        for number, value in enumerate(self.objects, 1):
            offsets.append(len(out)); out += b'%d 0 obj\n' % number + serialize(value) + b'\nendobj\n'
        position = len(out)
        out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(offsets) + 1) + b''.join(b'%010d 00000 n \n' % o for o in offsets)
        out += b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(offsets) + 1, position)
        return bytes(out)

    def save(self, path):
        with open(path, 'xb') as stream: stream.write(self.bytes())


def document(texts=('',), size=(595, 842), font_size=11, position=(50, 80), rotations=None, toc=None):
    writer = Writer(); font = writer.add({'Type': Name('Font'), 'Subtype': Name('Type1'), 'BaseFont': Name('Helvetica'), 'Encoding': Name('WinAnsiEncoding')})
    for index, text in enumerate(texts):
        content = b'BT /F1 ' + serialize(font_size) + b' Tf ' + serialize(position[0]) + b' ' + serialize(size[1] - position[1]) + b' Td ' + serialize(text.encode('cp1252')) + b' Tj ET\n' if text else b''
        page = writer.add_page(*size, content, {'Font': {'F1': font}})
        if rotations: page['Rotate'] = rotations[index]
    if toc:
        tree = writer.add({'Type': Name('Outlines')}); refs = [writer.add({}) for _ in toc]
        for index, ((level, title, page), ref) in enumerate(zip(toc, refs)):
            assert level == 1, 'This fixture only needs top-level outlines'
            value = writer.objects[ref.number - 1]; value.update(Title=title.encode(), Parent=tree, Dest=[writer.page_refs[page - 1], Name('Fit')])
            if index: value['Prev'] = refs[index - 1]
            if index + 1 < len(refs): value['Next'] = refs[index + 1]
        writer.objects[tree.number - 1].update(First=refs[0], Last=refs[-1], Count=len(refs)); writer.objects[writer.root.number - 1]['Outlines'] = tree
    return writer


def add_content(writer, page, content):
    old = page.get('Contents'); page['Contents'] = (list(old) if isinstance(old, list) else [old] if old else []) + [writer.stream(content)]


def add_image(writer, page, pixels, width, height, rect):
    ref = writer.stream(pixels, Type=Name('XObject'), Subtype=Name('Image'), Width=width, Height=height, ColorSpace=Name('DeviceRGB'), BitsPerComponent=8)
    page['Resources'].setdefault('XObject', {})['I1'] = ref; x0, y0, x1, y1 = rect
    add_content(writer, page, b'q ' + b' '.join(serialize(n) for n in (x1 - x0, 0, 0, y1 - y0, x0, page['MediaBox'][3] - y1)) + b' cm /I1 Do Q\n')


def add_link(writer, page):
    page.setdefault('Annots', []).append(writer.add({'Type': Name('Annot'), 'Subtype': Name('Link'), 'Rect': [40, 435, 125, 458], 'Border': [0, 0, 0], 'A': {'S': Name('URI'), 'URI': b'https://example.org'}}))


def core(*arguments, password=None):
    """The document core's answer as bytes; a refusal raises ValueError with its reason."""
    from lumen_office import program
    environment = dict(os.environ, LUMEN_PDF_PASSWORD_STDIN='1') if password is not None else None
    result = subprocess.run([program(), *map(str, arguments)], input=(password + '\n').encode() if password is not None else None,
                            capture_output=True, env=environment, timeout=120)
    if result.returncode: raise ValueError(result.stderr.decode(errors='replace').strip())
    return result.stdout


def saved(source):
    """A path for a writer, raw PDF bytes or a path; temporary files are removed when the test process ends."""
    if isinstance(source, (str, Path)): return Path(source)
    data = source.bytes() if isinstance(source, Writer) else source
    handle, name = tempfile.mkstemp(prefix='lumen-test-', suffix='.pdf'); os.write(handle, data); os.close(handle)
    import atexit; atexit.register(lambda: Path(name).unlink(missing_ok=True))
    return Path(name)


def render(source, scale=1, page=0, password=None):
    """The page as the core draws it, as a QImage."""
    from PySide6.QtGui import QColorSpace, QImage
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / 'page.png'
        core('pdf-render', saved(source), page, scale, target, password=password)
        # Plain values, as the core wrote them; a colour space would make Qt convert them.
        image = QImage(str(target)); image.setColorSpace(QColorSpace())
        return image.copy()


def pages(source, password=None):
    """Width, height and words of every page: left, top, right, bottom, text and line."""
    return json.loads(core('pdf-words', saved(source), 0, 10000, password=password))


def text(source, page=0):
    lines = {}
    for word in pages(source)[page]['words']: lines.setdefault(word[5], []).append(word[4])
    return '\n'.join(' '.join(words) for words in lines.values())


def info(source, password=None):
    return json.loads(core('pdf-info', saved(source), password=password))


def streams(path):
    """Every stream of a file, decompressed where it is Flate-coded: to see that text is really gone."""
    data = Path(path).read_bytes(); found = []
    for start in [i + 7 for i in range(len(data)) if data.startswith(b'stream\n', i)]:
        end = data.find(b'\nendstream', start); raw = data[start:end]
        try: found.append(zlib.decompress(raw))
        except zlib.error: found.append(raw)
    return found
