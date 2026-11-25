"""PDF constructs from ISO 32000 and PDF workflows, through the document core and without a foreign PDF engine."""
import json
from pathlib import Path
import re
import tempfile
import unittest

from document_workshop import export
from lumen_office import signature
from test_pdf_fixtures import Name, Ref, Stream, Writer, core, document, info, pages, render, saved, text


def toc(source):
    return json.loads(core('pdf-reader', saved(source), 'metadata'))['toc']


def translated(source, parts, folder, name='out.pdf'):
    """Every block of `source` replaced by `parts` (one list per block), written by the core."""
    import translate_pdf
    manifest = translate_pdf.inspect(saved(source)); output = Path(folder) / name
    translate_pdf.write(manifest, {s['id']: parts[int(s['id'])] for s in manifest['segments']}, output)
    return manifest, output


class ExtendedPDFTest(unittest.TestCase):
    def test_undefined_outline_reference_is_pdf_null(self):
        writer = Writer(); writer.add_page(20, 20)
        writer.objects[writer.root.number - 1]['Outlines'] = Ref(999)
        self.assertEqual(toc(writer.bytes()), [])

    def test_rotated_mirrored_text_keeps_words_and_selection_boxes(self):
        for matrix in ('0 1 -1 0 80 20', '-1 0 0 1 150 60', '.7071 .7071 -.7071 .7071 50 50'):
            writer = Writer(); writer.add_page(200, 200, ('BT /F 16 Tf ' + matrix + ' Tm (Alpha beta) Tj ET').encode(),
                {'Font': {'F': {'Type': Name('Font'), 'Subtype': Name('Type1'), 'BaseFont': Name('Helvetica')}}})
            data = writer.bytes(); words = pages(data)[0]['words']
            self.assertEqual([w[4] for w in words], ['Alpha', 'beta'])
            for scale in (1, 2):
                image = render(data, scale)
                for word in words:
                    x0, y0, x1, y1 = (int(v * scale) for v in word[:4])
                    self.assertTrue(any(image.pixelColor(x, y).red() < 100 for y in range(max(0, y0), min(image.height(), y1 + 1)) for x in range(max(0, x0), min(image.width(), x1 + 1))))

    def test_bitmaps_decode_arrays_stencils_and_soft_masks(self):
        def draw(raw, **attrs):
            writer = Writer()
            mask = attrs.pop('soft', None)
            if mask is not None: attrs['SMask'] = writer.stream(mask, Type=Name('XObject'), Subtype=Name('Image'), Width=2, Height=1, BitsPerComponent=8, ColorSpace=Name('DeviceGray'))
            ref = writer.stream(raw, Type=Name('XObject'), Subtype=Name('Image'), Width=2, Height=1, **attrs)
            writer.add_page(100, 50, b'0 0 1 rg 0 0 100 50 re f 1 0 0 rg 100 0 0 50 0 0 cm /I Do', {'XObject': {'I': ref}})
            return render(writer.bytes())
        for bits, raw in [(1, b'\x40'), (2, b'\x30'), (4, b'\x0f'), (8, b'\0\xff'), (16, b'\0\0\xff\xff')]:
            image = draw(raw, BitsPerComponent=bits, ColorSpace=Name('DeviceGray'), Decode=[1, 0])
            self.assertEqual(image.pixelColor(20, 25).name(), '#ffffff')
            self.assertEqual(image.pixelColor(80, 25).name(), '#000000')
        image = draw(b'\x40', ImageMask=True)
        self.assertEqual(image.pixelColor(20, 25).name(), '#ff0000')
        self.assertEqual(image.pixelColor(80, 25).name(), '#0000ff')
        image = draw(b'\xff\0\0\xff\0\0', BitsPerComponent=8, ColorSpace=Name('DeviceRGB'), soft=b'\0\x80')
        self.assertEqual(image.pixelColor(20, 25).name(), '#0000ff')
        self.assertLess(abs(image.pixelColor(80, 25).red() - 128), 2)
        self.assertLess(abs(image.pixelColor(80, 25).blue() - 127), 2)
        image = draw(b'\0\xff', BitsPerComponent=8, ColorSpace=[Name('Indexed'), Name('DeviceRGB'), 1, b'\xff\0\0\0\xff\0'])
        self.assertEqual(image.pixelColor(20, 25).name(), '#ff0000')
        self.assertEqual(image.pixelColor(80, 25).name(), '#00ff00')
        image = draw(b'\xff\0\0\0\xff\0', BitsPerComponent=8, ColorSpace=Name('DeviceRGB'), Mask=[255, 255, 0, 0, 0, 0])
        self.assertEqual(image.pixelColor(20, 25).name(), '#0000ff')
        self.assertEqual(image.pixelColor(80, 25).name(), '#00ff00')

    def test_colour_functions_palettes_and_calibration(self):
        def colour(space, values):
            writer = Writer()
            writer.add_page(10, 10, b'/S cs ' + ' '.join(map(str, values)).encode() + b' sc 0 0 10 10 re f', {'ColorSpace': {'S': space}})
            return render(writer.bytes()).pixelColor(5, 5)
        tint = {'FunctionType': 2, 'Domain': [0, 1], 'C0': [1, 1, 1], 'C1': [1, 0, 0], 'N': 1}
        self.assertEqual(colour([Name('Separation'), Name('Red'), Name('DeviceRGB'), tint], [1]).name(), '#ff0000')
        self.assertEqual(colour([Name('Separation'), Name('Red'), Name('DeviceRGB'), tint], [.5]).getRgb()[:3], (255, 128, 128))
        self.assertEqual(colour([Name('Indexed'), Name('DeviceRGB'), 1, b'\xff\0\0\0\xff\0'], [1]).name(), '#00ff00')
        for kind, sample in [('CalGray', [1]), ('Lab', [100, 0, 0])]:
            self.assertEqual(colour([Name(kind), {'WhitePoint': [.95047, 1, 1.08883]}], sample).name(), '#ffffff')
        sampled = Stream({'FunctionType': 0, 'Domain': [0, 1], 'Range': [0, 1], 'Size': [2], 'BitsPerSample': 8}, bytes([0, 255]))
        calculator = Stream({'FunctionType': 4, 'Domain': [0, 1], 'Range': [0, 1]}, b'{dup .5 gt {1 exch sub} if}')
        for function, value, grey in ((sampled, .25, 64), (calculator, .75, 64)):
            writer = Writer(); ref = writer.add(function)
            writer.add_page(10, 10, b'/S cs ' + str(value).encode() + b' sc 0 0 10 10 re f', {'ColorSpace': {'S': [Name('Separation'), Name('Ink'), Name('DeviceGray'), ref]}})
            self.assertLessEqual(abs(render(writer.bytes()).pixelColor(5, 5).red() - grey), 1)
        for broken in (b'{1 0 div}', b'{dup mul}} ignored'):
            writer = Writer(); ref = writer.add(Stream(dict(calculator.attrs), broken))
            writer.add_page(10, 10, b'/S cs .5 sc 0 0 10 10 re f', {'ColorSpace': {'S': [Name('Separation'), Name('Ink'), Name('DeviceGray'), ref]}})
            with self.assertRaises(ValueError): render(writer.bytes())

    def test_named_destinations_and_reordered_export(self):
        writer = Writer()
        first = writer.add_page(100, 120); writer.add_page(100, 120)
        target = [writer.page_refs[1], Name('XYZ'), 10, 100, None]
        leaf = writer.add({'Names': [b'chapter', {'D': target}]})
        writer.objects[writer.root.number - 1]['Names'] = {'Dests': {'Kids': [leaf]}}
        outline = writer.add({'Title': b'Chapter', 'Dest': b'chapter'})
        writer.objects[writer.root.number - 1]['Outlines'] = {'First': outline}
        first['Annots'] = [writer.add({'Subtype': Name('Link'), 'Rect': [1, 1, 20, 10], 'A': {'S': Name('GoTo'), 'D': b'chapter'}})]
        source = saved(writer.bytes())
        self.assertEqual(toc(source), [[1, 'Chapter', 2]])
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'reordered.pdf'; stamp = signature(source)
            export([dict(path=str(source), page=1, rotation=0, boxes=[], stamp=stamp), dict(path=str(source), page=0, rotation=0, boxes=[], stamp=stamp)], output)
            data = output.read_bytes()
            kids = re.search(rb'/Kids \[(\d+) 0 R (\d+) 0 R\]', data).groups()
            # The link on the former first page now points at the output's first page, with its view kept.
            self.assertRegex(data, rb'/D \[' + kids[0] + rb' 0 R /XYZ 10 100 null\]')

    def test_page_units_are_applied_and_preserved(self):
        writer = Writer(); page = writer.add_page(20, 30, b'1 0 0 rg 0 0 10 10 re f')
        page['UserUnit'] = 2
        source = saved(writer.bytes()); found = pages(source)[0]
        self.assertEqual((found['width'], found['height']), (40, 60))
        self.assertEqual(render(source).pixelColor(15, 45).name(), '#ff0000')
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'turned.pdf'
            export([dict(path=str(source), page=0, rotation=90, boxes=[], stamp=signature(source))], output)
            found = pages(output)[0]; self.assertEqual((found['width'], found['height']), (60, 40))

    def test_password_files(self):
        for file in (Path(__file__).parent / 'fixtures/pdf').glob('*.pdf'):
            with self.subTest(file=file.name):
                for password in ('test-reader-pass', 'test-owner-pass'):
                    self.assertEqual(info(file, password=password)['pages'], 2)
                    self.assertEqual(pages(file, password=password)[0]['words'][0][4], 'First')
                for password in ('wrong', None):
                    with self.assertRaises(ValueError): info(file, password=password)

    def test_translation_sets_unicode_styles_and_defined_text_state(self):
        # One block as wide as the old test's text box: thirty capital Ms at 20 points.
        wide = document(['M' * 30], size=(600, 180), font_size=20, position=(20, 60)).bytes()
        with tempfile.TemporaryDirectory() as folder:
            for index, sample in enumerate(['office affinity ffi ff fi ﬃ', 'A 𝕏 𝕐 ℤ end', 'á è ẍ', 'é á̧ test', 'Grüezi café Ελληνικά']):
                _, output = translated(wide, [[sample]], folder, f'{index}.pdf')
                self.assertEqual(text(output), sample)
            bold = {'Type': Name('Font'), 'Subtype': Name('Type1'), 'BaseFont': Name('Helvetica-Bold')}
            plain = {'Type': Name('Font'), 'Subtype': Name('Type1'), 'BaseFont': Name('Helvetica')}
            writer = Writer(); writer.add_page(600, 180, b'BT /B 20 Tf 20 120 Td (Bold ) Tj /R 20 Tf (normal ) Tj /B 20 Tf (again) Tj ET', {'Font': {'B': bold, 'R': plain}})
            manifest, output = translated(writer.bytes(), [['Fett ', 'normal ', 'wieder']], folder, 'styles.pdf')
            self.assertEqual([style['bold'] for style in manifest['segments'][0]['styles']], [True, False, True])
            self.assertEqual(text(output), 'Fett normal wieder')
            embedded = set(re.findall(rb'/(LumenFont\d+(?:-Bold)?) \d+ 0 R', Path(output).read_bytes()))
            self.assertEqual(sorted(name.endswith(b'-Bold') for name in embedded), [False, True])
            with self.assertRaises(ValueError): translated(wide, [['مرحبا']], folder, 'rtl.pdf')
            for index, transform in enumerate((b'1 0 0 1 120 0 cm', b'2 0 0 2 0 0 cm', b'3 Tr')):
                writer = document(); page = writer.objects[writer.page_refs[0].number - 1]; page['Contents'] = writer.stream(transform + b' BT /F1 20 Tf 30 150 Td (Hello) Tj ET')
                manifest, output = translated(writer.bytes(), [['Hallo']], folder, f'state{index}.pdf')
                words = pages(output)[0]['words']
                self.assertEqual(text(output), 'Hallo'); self.assertLess(abs(words[0][0] - manifest['segments'][0]['rect'][0]), 1)
                # Even invisible source text comes back visible.
                x0, y0, x1, y1 = (int(v) for v in words[0][:4]); image = render(output)
                self.assertTrue(any(image.pixelColor(x, y).red() < 100 for y in range(y0, y1) for x in range(x0, x1)))

    def test_annotations_do_not_inherit_page_transform_or_clip(self):
        writer = document(['Linked']); page = writer.objects[writer.page_refs[0].number - 1]
        page['Annots'] = [writer.add({'Subtype': Name('Link'), 'Rect': [1, 1, 10, 10], 'Dest': b'named-page'})]
        source = saved(writer.bytes())
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            export([dict(path=str(source), page=0, rotation=0, boxes=[], stamp=signature(source))], Path(folder) / 'out.pdf')
        for content in (b'1 0 0 1 100 0 cm', b'0 0 5 5 re W n'):
            writer = Writer(); page = writer.add_page(200, 200, content); appearance = writer.stream(b'1 0 0 rg 0 0 20 20 re f', Type=Name('XObject'), Subtype=Name('Form'), BBox=[0, 0, 20, 20])
            page['Annots'] = [writer.add({'Type': Name('Annot'), 'Subtype': Name('Stamp'), 'Rect': [20, 20, 40, 40], 'AP': {'N': appearance}})]
            image = render(writer.bytes()); self.assertEqual(image.pixelColor(30, 170).name(), '#ff0000'); self.assertEqual(image.pixelColor(130, 170).name(), '#ffffff')

    def test_legacy_anchors_preserve_notes_and_rebuild_utf16_selection(self):
        from reader_data import CorePage, ENGINE, reanchor

        class Read:
            def __init__(self, source): self.pages = pages(source)
            def __len__(self): return len(self.pages)
            def page(self, index): return CorePage([w[:5] + [0, w[5]] for w in self.pages[index]['words']])
        with tempfile.TemporaryDirectory() as folder:
            _, output = translated(document(['x before Hello world']), [['𝕏 before Hello world']], folder)
            note = dict(id='old', page=0, text='Hello world', note='private note', words=[], selection=[5, 16]); result = reanchor(Read(output), [note])[0]
        self.assertEqual(result['selection'], [10, 21]); self.assertEqual(result['legacy_anchor']['selection'], [5, 16]); self.assertEqual(result['note'], 'private note'); self.assertEqual(result['engine'], ENGINE)
        bounded = reanchor(Read(document(['planet net']).bytes()), [dict(note, text='net', selection=[7, 10])])[0]; self.assertEqual(bounded['selection'], [7, 10])
        result = reanchor(Read(document(['Hello world Hello world']).bytes()), [note])[0]
        self.assertEqual(result['anchor_status'], 'unresolved'); self.assertEqual(result['words'], []); self.assertEqual(result['selection'], []); self.assertEqual(result['text'], note['text'])
        with tempfile.TemporaryDirectory() as folder:
            from lumen_reflow import ReflowBook
            path = Path(folder) / 'book.txt'; path.write_text('Hello world\n' + 'Another paragraph.\n' * 100)
            with ReflowBook(path) as book:
                result = reanchor(book, [dict(note, page=999)], True)[0]; self.assertEqual(result['page'], 0); self.assertEqual(result['legacy_anchor']['page'], 999)

    def test_full_text_counts_characters_and_worker_keeps_inherited_limits(self):
        import subprocess, sys
        from tools_data import document_text
        from tools_ui import Job
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'unicode.pdf'; document(['ä' * 2000] * 32 + ['FINAL_SENTINEL']).save(path)
            found = document_text(path, Job(lambda _: None)); self.assertIn('FINAL_SENTINEL', found); self.assertEqual(found.count('ä'), 64000)
            too_long = Path(folder) / 'too-long.pdf'; document(['ä' * 2000] * 61).save(too_long)
            with self.assertRaises(ValueError): document_text(too_long, Job(lambda _: None))
            code = 'import resource;resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3));from lumen_office import limits;limits();assert resource.getrlimit(resource.RLIMIT_AS)==(1024**3,1024**3)'
            subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).parent, check=True, capture_output=True, timeout=10)


if __name__ == '__main__': unittest.main()
