"""Synthetic-only checks of whitespace proposals and the visual review gate."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

SCRIPTS = Path(__file__).resolve().parents[1] / 'assets/package/scripts'
sys.path.insert(0, str(SCRIPTS))
import prepare_print_views as views
import print_sheets


class PrintViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-print-views-')
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def source(self):
        path = self.root / 'source.pdf'
        drawing = canvas.Canvas(str(path), pagesize=(400, 600))
        drawing.drawString(60, 300, 'SYNTHETIC BODY')
        drawing.setFillGray(.995)
        drawing.rect(50, 50, 5, 5, fill=1, stroke=0)
        drawing.save()
        return path

    def manifest(self, path, kind='evidence', extra=None):
        document = {'id': 'synthetic-document', 'path': path.name, 'role': 'invoice'}
        document.update(extra or {})
        data = {'schema_version': 1, 'sections': [{'id': 'synthetic-section', 'kind': kind,
                'layout': 'grid_2x2', 'documents': [document]}]}
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        return path

    def test_light_mark_survives_padding(self):
        image = Image.new('RGB', (500, 500), 'white')
        draw = ImageDraw.Draw(image)
        draw.rectangle((100, 100, 300, 300), fill='black')
        image.putpixel((450, 450), (254, 254, 254))
        crop, ink = views.exterior_crop(image)
        self.assertEqual(ink, [100, 100, 451, 451])
        self.assertGreater(crop[2], 451 / 500)
        self.assertGreater(crop[3], 451 / 500)

    def test_blank_page_is_not_cropped(self):
        crop, ink = views.exterior_crop(Image.new('RGB', (50, 80), 'white'))
        self.assertEqual(crop, [0, 0, 1, 1])
        self.assertIsNone(ink)

    def test_proposal_requires_review_and_preserves_sources(self):
        source = self.source()
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest = self.manifest(source)
        output = self.root / 'new-proposals'
        report = views.prepare(manifest, output, 144)
        proposed = output / 'print-manifest.proposed.json'
        data = json.loads(proposed.read_text(encoding='utf-8'))
        document = data['sections'][0]['documents'][0]
        self.assertEqual((output / document['path']).resolve(), source)
        self.assertFalse(document['views']['1']['reviewed'])
        self.assertLess(document['views']['1']['crop'][0], .125)
        self.assertGreater(document['views']['1']['crop'][3], .916)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        self.assertEqual(report['records'][0]['source_sha256'], before)
        self.assertTrue((output / 'contact-sheet.png').is_file())
        self.assertTrue((output / report['records'][0]['preview']).is_file())
        with self.assertRaisesRegex(ValueError, 'reviewed:true'):
            print_sheets.inspect_manifest(proposed)
        document['views']['1']['reviewed'] = True
        proposed.write_text(json.dumps(data), encoding='utf-8')
        print_sheets.inspect_manifest(proposed)
        with self.assertRaises(FileExistsError):
            views.prepare(manifest, output)

    def test_reviewed_view_and_form_geometry_stay_unchanged(self):
        source = self.source()
        explicit = {'crop': [.1, .1, .9, .9], 'rotation': 90, 'reviewed': True}
        manifest = self.manifest(source, extra={'views': {'1': explicit}})
        out = self.root / 'retained'
        report = views.prepare(manifest, out)
        data = json.loads((out / 'print-manifest.proposed.json').read_text())
        self.assertEqual(data['sections'][0]['documents'][0]['views']['1'], explicit)
        self.assertEqual(report['records'][0]['status'], 'existing_reviewed_view_retained')
        manifest = self.manifest(source, kind='forms')
        out = self.root / 'forms'
        report = views.prepare(manifest, out)
        data = json.loads((out / 'print-manifest.proposed.json').read_text())
        self.assertNotIn('views', data['sections'][0]['documents'][0])
        self.assertEqual(report['records'][0]['status'], 'form_geometry_unchanged')

    def test_page_selection_rotation_and_images(self):
        source = self.source()
        page = PdfReader(source).pages[0]
        page.rotate(90)
        rotated = self.root / 'rotated.pdf'
        writer = PdfWriter()
        writer.add_page(page)
        writer.write(rotated)
        report = views.prepare(self.manifest(rotated, extra={'pages': [1]}), self.root / 'rotated-views', 72)
        self.assertEqual(report['records'][0]['render_size_pixels'], [600, 400])
        image_path = self.root / 'image.png'
        im = Image.new('RGB', (500, 300), 'white')
        ImageDraw.Draw(im).rectangle((150, 100, 350, 200), fill='black')
        im.save(image_path)
        report = views.prepare(self.manifest(image_path), self.root / 'image-views', 72)
        self.assertEqual(report['records'][0]['render_size_pixels'], [500, 300])
        self.assertEqual(report['records'][0]['status'], 'proposal_requires_visual_review')

    def test_bad_selection_fails_without_output(self):
        source = self.source()
        manifest = self.manifest(source, extra={'pages': [2]})
        out = self.root / 'bad'
        with self.assertRaisesRegex(ValueError, 'page selection'):
            views.prepare(manifest, out)
        self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
