"""Synthetic ISO 32000 transparency and shading regressions; no PDF backend oracle."""
import unittest

from lumen_pdf import Document, Name, Writer
from lumen_pdf_page import Page


class PDFTransparencyTest(unittest.TestCase):
    def assert_pixels(self, document, expected):
        page = Page(document, 0)
        for scale in (1, 2):
            image = page.render(scale)
            for x, y, rgb in expected:
                # Expectations use PDF coordinates, away from antialiased edges.
                actual = image.pixelColor(int(x * scale), int((page.height - y) * scale))
                with self.subTest(scale=scale, x=x, y=y):
                    for value, target in zip(actual.getRgb()[:3], rgb):
                        # Gradients sample pixel centres and may quantize lookup
                        # tables; seven levels still distinguish every case here.
                        self.assertLessEqual(abs(value - target), 7, (actual.getRgb(), rgb))

    def test_page_group_keeps_fill_and_stroke_opacity(self):
        writer = Writer()
        page = writer.add_page(100, 60,
            b'/Half gs 1 0 0 rg 10 10 20 20 re f '
            b'0 0 1 RG 10 w 50 20 m 90 20 l S',
            {'ExtGState': {'Half': {'ca': .5, 'CA': .5}}})
        page['Group'] = writer.add({'S': Name('Transparency'), 'CS': Name('DeviceRGB')})
        self.assert_pixels(Document(writer.bytes()), [
            (20, 20, (255, 128, 128)), (70, 20, (128, 128, 255)),
            (20, 45, (255, 255, 255)),
        ])

    def test_graphics_state_restores_opacity_with_q_and_Q(self):
        writer = Writer()
        writer.add_page(100, 60,
            b'1 0 0 rg /Half gs q /Quarter gs 0 0 30 60 re f Q '
            b'35 0 30 60 re f /Solid gs 70 0 30 60 re f',
            {'ExtGState': {'Half': {'ca': .5}, 'Quarter': {'ca': .25}, 'Solid': {'ca': 1}}})
        self.assert_pixels(Document(writer.bytes()), [
            (15, 30, (255, 191, 191)), (50, 30, (255, 128, 128)),
            (85, 30, (255, 0, 0)),
        ])

    def test_axial_shading_without_extend_leaves_background(self):
        writer = Writer()
        shading = writer.add({'ShadingType': 2, 'ColorSpace': Name('DeviceRGB'),
            'Coords': [20, 0, 80, 0], 'Extend': [False, False],
            'Function': {'FunctionType': 2, 'Domain': [0, 1],
                         'C0': [1, 0, 0], 'C1': [0, 0, 1], 'N': 1}})
        writer.add_page(100, 60, b'0 1 0 rg 0 0 100 60 re f /Shade sh',
                        {'Shading': {'Shade': shading}})
        self.assert_pixels(Document(writer.bytes()), [
            (10, 30, (0, 255, 0)), (35, 30, (191, 0, 64)),
            (65, 30, (64, 0, 191)), (90, 30, (0, 255, 0)),
        ])

    def test_stitched_axial_shading_extends_endpoint_colours(self):
        writer = Writer()
        function = {'FunctionType': 3, 'Domain': [0, 1], 'Bounds': [.5], 'Encode': [0, 1, 0, 1],
            'Functions': [
                {'FunctionType': 2, 'Domain': [0, 1], 'C0': [1, 0, 0], 'C1': [0, 1, 0], 'N': 1},
                {'FunctionType': 2, 'Domain': [0, 1], 'C0': [0, 1, 0], 'C1': [0, 0, 1], 'N': 1}]}
        shading = writer.add({'ShadingType': 2, 'ColorSpace': Name('DeviceRGB'),
            'Coords': [20, 0, 80, 0], 'Function': function, 'Extend': [True, True]})
        writer.add_page(100, 60, b'/Shade sh', {'Shading': {'Shade': shading}})
        self.assert_pixels(Document(writer.bytes()), [
            (10, 30, (255, 0, 0)), (35, 30, (128, 128, 0)),
            (65, 30, (0, 128, 128)), (90, 30, (0, 0, 255)),
        ])

    def test_shading_pattern_matrix_uses_default_page_space(self):
        writer = Writer()
        pattern = writer.add({'Type': Name('Pattern'), 'PatternType': 2,
            'Matrix': [0, 2, -1, 0, 100, 10],
            'Shading': {'ShadingType': 2, 'ColorSpace': Name('DeviceRGB'),
                'Coords': [0, 0, 40, 0], 'Extend': [True, True],
                'Function': {'FunctionType': 2, 'Domain': [0, 1],
                             'C0': [1, 0, 0], 'C1': [0, 0, 1], 'N': 1}}})
        writer.add_page(100, 100,
            b'1 0 0 2 0 0 cm /Pattern cs /Gradient scn 0 0 100 50 re f',
            {'Pattern': {'Gradient': pattern}})
        # The pattern rotates its axis into y=10..90; the content's y scale
        # changes the rectangle but must not scale the pattern a second time.
        self.assert_pixels(Document(writer.bytes()), [
            (50, 30, (191, 0, 64)), (50, 70, (64, 0, 191)),
        ])

    def test_isolated_form_applies_parent_alpha_once_after_overlap(self):
        writer = Writer()
        form = writer.stream(b'1 0 0 rg 10 10 50 40 re f 0 0 1 rg 40 10 50 40 re f',
            Type=Name('XObject'), Subtype=Name('Form'), BBox=[0, 0, 100, 60],
            Group={'S': Name('Transparency'), 'CS': Name('DeviceRGB'), 'I': True}, Resources={})
        writer.add_page(100, 60, b'/Half gs /Group Do',
            {'ExtGState': {'Half': {'ca': .5}}, 'XObject': {'Group': form}})
        self.assert_pixels(Document(writer.bytes()), [
            (20, 30, (255, 128, 128)), (50, 30, (128, 128, 255)),
            (80, 30, (128, 128, 255)), (5, 30, (255, 255, 255)),
        ])

    def test_knockout_group_replaces_earlier_objects_with_its_backdrop(self):
        writer = Writer()
        form = writer.stream(b'1 0 0 rg 10 10 50 40 re f /Half gs 0 0 1 rg 40 10 50 40 re f',
            Type=Name('XObject'), Subtype=Name('Form'), BBox=[0, 0, 100, 60],
            Group={'S': Name('Transparency'), 'CS': Name('DeviceRGB'), 'K': True},
            Resources={'ExtGState': {'Half': {'ca': .5}}})
        writer.add_page(100, 60, b'/Group Do', {'XObject': {'Group': form}})
        # Without knockout the overlap would mix blue into red: (128, 0, 128).
        self.assert_pixels(Document(writer.bytes()), [
            (20, 30, (255, 0, 0)), (50, 30, (128, 128, 255)), (80, 30, (128, 128, 255)),
        ])

    def test_group_that_is_not_isolated_takes_outer_opacity_once(self):
        writer = Writer()
        form = writer.stream(b'1 0 0 rg 10 10 50 40 re f 0 1 0 rg 40 10 50 40 re f',
            Type=Name('XObject'), Subtype=Name('Form'), BBox=[0, 0, 100, 60],
            Group={'S': Name('Transparency'), 'CS': Name('DeviceRGB')}, Resources={})
        writer.add_page(100, 60, b'/Half gs /Group Do',
            {'ExtGState': {'Half': {'ca': .5}}, 'XObject': {'Group': form}})
        self.assert_pixels(Document(writer.bytes()), [
            (20, 30, (255, 128, 128)), (50, 30, (128, 255, 128)), (80, 30, (128, 255, 128)),
        ])

    def test_coloured_tiling_pattern_repeats_its_cell(self):
        writer = Writer()
        cell = writer.stream(b'1 0 0 rg 0 0 10 20 re f', Type=Name('Pattern'), PatternType=1, PaintType=1,
            TilingType=1, BBox=[0, 0, 20, 20], XStep=20, YStep=20, Resources={})
        writer.add_page(100, 60, b'/Pattern cs /Tile scn 0 0 100 40 re f', {'Pattern': {'Tile': cell}})
        self.assert_pixels(Document(writer.bytes()), [
            (5, 10, (255, 0, 0)), (15, 10, (255, 255, 255)), (45, 30, (255, 0, 0)),
            (55, 30, (255, 255, 255)), (45, 50, (255, 255, 255)),
        ])

    def test_graphics_state_sets_line_style_and_ignores_overprint(self):
        writer = Writer()
        writer.add_page(100, 60, b'/Line gs 20 30 m 60 30 l S',
            {'ExtGState': {'Line': {'LW': 10, 'LC': 1, 'LJ': 1, 'ML': 4, 'OP': True, 'op': True, 'OPM': 1, 'AIS': False}}})
        # The round cap reaches four units past the end of the line.
        self.assert_pixels(Document(writer.bytes()), [
            (40, 30, (0, 0, 0)), (17, 30, (0, 0, 0)), (63, 30, (0, 0, 0)), (12, 30, (255, 255, 255)),
        ])

    def test_layer_switched_off_by_default_is_neither_drawn_nor_read(self):
        writer = Writer()
        font = {'Type': Name('Font'), 'Subtype': Name('Type1'), 'BaseFont': Name('ArialMT'), 'Encoding': Name('WinAnsiEncoding')}
        hidden = writer.add({'Type': Name('OCG'), 'Name': b'Entwurf'})
        shown = writer.add({'Type': Name('OCG'), 'Name': b'Inhalt'})
        stamp = writer.stream(b'0 1 0 rg 70 10 20 20 re f', Type=Name('XObject'), Subtype=Name('Form'),
            BBox=[0, 0, 100, 60], OC=hidden, Resources={})
        empty = writer.stream(b'0 1 0 rg 0 0 100 60 re f', Type=Name('XObject'), Subtype=Name('Form'),
            BBox=[10, 10, 10, 30], Resources={})
        writer.add_page(100, 60,
            b'/OC /Off BDC 1 0 0 rg 10 10 20 20 re f BT /F1 8 Tf 10 50 Td (geheim) Tj ET EMC '
            b'/OC /On BDC 0 0 1 rg 40 10 20 20 re f BT /F1 8 Tf 40 50 Td (sichtbar) Tj ET EMC /Stamp Do /Empty Do',
            {'Font': {'F1': font}, 'Properties': {'Off': hidden, 'On': shown}, 'XObject': {'Stamp': stamp, 'Empty': empty}})
        document = Document(writer.bytes())
        document.catalog['OCProperties'] = {'OCGs': [hidden, shown], 'D': {'OFF': [hidden]}}
        self.assert_pixels(document, [(20, 20, (255, 255, 255)), (50, 20, (0, 0, 255)), (80, 20, (255, 255, 255))])
        # The font the file does not carry is replaced, and only the visible layer is read.
        self.assertEqual(Page(document, 0).text(), 'sichtbar')
        document.catalog['OCProperties']['D'] = {'BaseState': Name('OFF'), 'ON': [hidden]}
        self.assertEqual(Page(document, 0).text(), 'geheim')

    def test_soft_masks_capture_gs_transform_and_none_removes_mask(self):
        for subtype in ('Alpha', 'Luminosity'):
            with self.subTest(subtype=subtype):
                writer = Writer()
                content = (b'/Half gs 1 g' if subtype == 'Alpha' else b'.5 g') + b' 0 0 20 60 re f'
                group = writer.stream(content, Type=Name('XObject'), Subtype=Name('Form'),
                    BBox=[0, 0, 20, 60], Matrix=[1, 0, 0, 1, 5, 0],
                    Group={'S': Name('Transparency'), 'CS': Name('DeviceRGB'), 'I': True},
                    Resources={'ExtGState': {'Half': {'ca': .5}}})
                mask = {'S': Name(subtype), 'G': group, 'BC': [0, 0, 0]}
                writer.add_page(100, 60,
                    b'0 0 1 rg 0 0 100 60 re f '
                    b'1 0 0 1 10 0 cm /Mask gs 1 0 0 1 20 0 cm '
                    b'1 0 0 rg -30 0 100 60 re f '
                    b'/Clear gs 0 1 0 rg 40 0 10 60 re f',
                    {'ExtGState': {'Mask': {'SMask': mask}, 'Clear': {'SMask': Name('None')}}})
                # The mask occupies page x=15..35 (form + gs transforms).
                # The later cm must neither move it to x=35..55 nor rescale it.
                self.assert_pixels(Document(writer.bytes()), [
                    (5, 30, (0, 0, 255)), (25, 30, (128, 0, 128)),
                    (45, 30, (0, 0, 255)), (75, 30, (0, 255, 0)),
                ])

    def test_copy_page_preserves_transparency_group_and_pixels(self):
        writer = Writer()
        page = writer.add_page(100, 60, b'/Half gs 1 0 0 rg 0 0 100 60 re f',
                              {'ExtGState': {'Half': {'ca': .5}}})
        page['Group'] = writer.add({'S': Name('Transparency'), 'CS': Name('DeviceRGB'), 'I': True})
        source = Document(writer.bytes())
        copied = Writer()
        copied.copy_page(source, 0)
        result = Document(copied.bytes())
        self.assertEqual(result.resolve(result.pages[0]['Group']), source.resolve(source.pages[0]['Group']))
        self.assert_pixels(result, [(50, 30, (255, 128, 128))])

    def test_combined_fill_and_stroke_knocks_out_overlap(self):
        writer = Writer()
        writer.add_page(100, 80,
            b'/Half gs 1 0 0 rg 0 0 1 RG 20 w 20 20 60 40 re B',
            {'ExtGState': {'Half': {'ca': .5, 'CA': .5}}})
        # B is one composite object: the stroke knocks out the underlying fill,
        # rather than adding a second translucent layer where the two overlap.
        self.assert_pixels(Document(writer.bytes()), [
            (25, 40, (128, 128, 255)), (15, 40, (128, 128, 255)),
            (50, 40, (255, 128, 128)),
        ])

    def test_gray_page_group_converts_colours_to_its_blending_space(self):
        writer = Writer()
        page = writer.add_page(100, 60,
            b'1 0 0 rg 0 0 100 60 re f /Half gs 0 0 1 rg 0 0 50 60 re f',
            {'ExtGState': {'Half': {'ca': .5}}})
        page['Group'] = {'S': Name('Transparency'), 'CS': Name('DeviceGray'), 'I': True}
        rendered = Page(Document(writer.bytes()), 0)
        for scale in (1, 2):
            image = rendered.render(scale)
            for x in (25, 75):
                rgb = image.pixelColor(x * scale, 30 * scale).getRgb()[:3]
                # Exact device-colour conversions may vary with profiles, but
                # every output component must agree after a Gray blend group.
                with self.subTest(scale=scale, x=x):
                    self.assertLessEqual(max(rgb) - min(rgb), 2, rgb)
                    self.assertTrue(0 < rgb[0] < 255, rgb)

    def test_shading_pattern_background_fills_outside_unextended_axis(self):
        writer = Writer()
        pattern = {'PatternType': 2,
            'Shading': {'ShadingType': 2, 'ColorSpace': Name('DeviceRGB'),
                'Coords': [20, 0, 80, 0], 'Extend': [False, False], 'Background': [0, 1, 0],
                'Function': {'FunctionType': 2, 'Domain': [0, 1],
                             'C0': [1, 0, 0], 'C1': [0, 0, 1], 'N': 1}}}
        writer.add_page(100, 60, b'/Pattern cs /Gradient scn 0 0 100 60 re f',
                        {'Pattern': {'Gradient': pattern}})
        self.assert_pixels(Document(writer.bytes()), [
            (10, 30, (0, 255, 0)), (50, 30, (128, 0, 128)),
            (90, 30, (0, 255, 0)),
        ])


if __name__ == '__main__':
    unittest.main()
