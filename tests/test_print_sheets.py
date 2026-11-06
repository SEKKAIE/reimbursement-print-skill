"""Synthetic geometry, evidence coverage, pairing and print-status checks."""
from pathlib import Path
import importlib.util
import json
import tempfile
import unittest

from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

SCRIPT = Path(__file__).resolve().parents[1] / 'assets/package/scripts/print_sheets.py'
spec = importlib.util.spec_from_file_location('print_sheets', SCRIPT)
sheets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sheets)


class PrintSheetsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='synthetic-print-')
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def pdf(self, name, pages=1, size=(500, 300)):
        path = self.root / name
        c = canvas.Canvas(str(path), pagesize=size)
        for n in range(pages):
            for x, y, label in [(10, 10, 'BOTTOM'), (10, size[1] - 20, 'TOP'),
                                (size[0] - 90, size[1] - 20, 'RIGHT')]:
                c.drawString(x, y, f'{name}-{n + 1}-{label}')
            c.showPage()
        c.save()
        return path

    def document(self, number, **kwargs):
        path = self.pdf(f'input-{number}.pdf')
        return {'id': f'doc-{number}', 'path': path.name, **kwargs}

    def run_job(self, docs, layout='grid_2x2', orientation='portrait', output='out', **kwargs):
        data = {'schema_version': 1, 'sections': [{'id': 'test', 'kind': 'evidence',
                'layout': layout, 'orientation': orientation, 'documents': docs}]}
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(data), encoding='utf-8')
        return sheets.build(path, self.root / output, **kwargs)

    def test_four_images_two_shared_lines_no_piece_rectangles(self):
        docs = []
        for n in range(4):
            p = self.root / f'image-{n}.png'
            Image.new('RGB', (100, 180), (20 * n, 20 * n, 20 * n)).save(p)
            docs.append({'id': f'image-{n}', 'path': p.name})
        report = self.run_job(docs)
        output = report['outputs'][0]
        self.assertEqual(output['pages'], 1)
        self.assertEqual(output['pieces'], 4)
        self.assertEqual(output['sheets'][0]['guide_lines_mm'], [(105, 0, 105, 297), (0, 148.5, 210, 148.5)])
        page = PdfReader(self.root / 'out' / output['file']).pages[0]
        # Four raster images have no strokes; only the two shared cut lines stroke.
        operators = [op for _, op in page.get_contents().operations]
        self.assertEqual(operators.count(b'S'), 2)
        for placement in output['placements']:
            x, y, w, h = placement['slot_mm']
            left, bottom, right, top = placement['fitted_box_mm']
            self.assertGreaterEqual(left, x + 6 - 1e-6)
            self.assertLessEqual(right, x + w - 6 + 1e-6)
            self.assertGreaterEqual(bottom, y + 6 - 1e-6)
            self.assertLessEqual(top, y + h - 6 + 1e-6)

    def test_all_pdf_pages_exactly_once_and_last_slots_empty(self):
        path = self.pdf('multipage.pdf', 5)
        before = sheets.digest(path)
        report = self.run_job([{'id': 'multi', 'path': path.name}])
        output = report['outputs'][0]
        self.assertEqual(output['pages'], 2)
        self.assertEqual([s['used_slots'] for s in output['sheets']], [[1, 2, 3, 4], [1]])
        self.assertEqual(report['accounted_source_pages'], 5)
        self.assertEqual(report['prepared_unique_pages'], 5)
        text = ''.join(p.extract_text() for p in PdfReader(self.root / 'out' / output['file']).pages)
        for n in range(1, 6):
            for label in ['TOP', 'BOTTOM', 'RIGHT']:
                self.assertEqual(text.count(f'multipage.pdf-{n}-{label}'), 1)
        self.assertEqual(sheets.digest(path), before)

    def test_two_up_dimensions_margins_no_dimension_labels(self):
        report = self.run_job([self.document(1), self.document(2), self.document(3)], layout='two_up_136')
        output = report['outputs'][0]
        self.assertEqual(output['pages'], 2)
        self.assertEqual(output['placements'][0]['slot_mm'], [0, 161, 210, 136])
        self.assertEqual(output['placements'][1]['slot_mm'], [0, 25, 210, 136])
        self.assertEqual(output['sheets'][0]['guide_lines_mm'], [(0, 161, 210, 161), (0, 25, 210, 25)])
        text = ''.join(p.extract_text() for p in PdfReader(self.root / 'out' / output['file']).pages)
        self.assertNotIn('136', text)
        self.assertNotIn('210', text)

    def test_layout_defaults_and_forms_remain_separate(self):
        manifest = {'schema_version': 1, 'sections': [
            {'id': 'receipts', 'kind': 'evidence', 'documents': [self.document(1)]},
            {'id': 'covers', 'kind': 'forms', 'layout': 'two_up_136', 'documents': [self.document(2)]}
        ]}
        path = self.root / 'defaults.json'
        path.write_text(json.dumps(manifest))
        report = sheets.build(path, self.root / 'out')
        self.assertEqual([out['file'] for out in report['outputs']], ['evidence-receipts.pdf', 'forms-covers.pdf'])
        self.assertEqual([out['page_size_mm'] for out in report['outputs']], [[297, 210], [210, 297]])

    def test_pair_moves_to_complete_row_and_is_invoice_first(self):
        a, b = self.document(2, role='invoice', pair_id='ride'), self.document(3, role='itinerary', pair_id='ride')
        report = self.run_job([self.document(1), b, a, self.document(4)], orientation='landscape')
        p = report['outputs'][0]['placements']
        self.assertEqual([(v['id'], v['output_page'], v['slot']) for v in p],
                         [('doc-1', 1, 1), ('doc-2', 1, 3), ('doc-3', 1, 4), ('doc-4', 2, 1)])

    def test_incomplete_pair_rejected_before_outputs(self):
        with self.assertRaisesRegex(ValueError, 'pair requires'):
            self.run_job([self.document(1, role='invoice', pair_id='ride')])
        self.assertFalse((self.root / 'out').exists())

    def test_pair_can_print_only_outstanding_member_after_audited_exclusion(self):
        invoice = self.document(1, role='invoice', pair_id='ride')
        itinerary = self.document(2, role='itinerary', pair_id='ride')
        first = self.run_job([invoice, itinerary])
        ledger = json.loads((self.root / 'out/print-ledger.json').read_text())
        ledger['pages'][0].update(status='printed', confirmed_by='user', confirmation='User confirmed invoice printed')
        ledger_path = self.root / 'confirmed.json'
        ledger_path.write_text(json.dumps(ledger), encoding='utf-8')
        report = self.run_job([invoice, itinerary], output='remaining', printed_ledger=ledger_path)
        self.assertEqual(report['prepared_unique_pages'], 1)
        self.assertEqual(report['outputs'][0]['placements'][0]['id'], 'doc-2')
        self.assertEqual(report['documents'][1]['pages'][0]['pair_counterpart_exclusion'],
                         {'id': 'doc-1', 'page': 1, 'disposition': 'already_printed'})
        report = self.run_job([{**invoice, 'print': False}, itinerary], output='excluded')
        self.assertEqual(report['prepared_unique_pages'], 1)
        self.assertEqual(report['documents'][1]['pages'][0]['pair_counterpart_exclusion']['disposition'], 'print_false')

    def test_declared_pair_still_validated_when_member_excluded(self):
        invoice = self.document(1, role='invoice', pair_id='ride', print=False)
        wrong = self.document(2, role='invoice', pair_id='ride')
        with self.assertRaisesRegex(ValueError, 'pair requires'):
            self.run_job([invoice, wrong])

    def test_duplicate_print_false_and_page_selection_are_audited(self):
        a = self.document(1)
        multi = self.pdf('multiple.pdf', 3)
        docs = [a, {**a, 'id': 'copy'}, self.document(2, print=False),
                {'id': 'selected', 'path': multi.name, 'pages': [2]}]
        report = self.run_job(docs)
        self.assertEqual(report['prepared_unique_pages'], 2)
        self.assertEqual(report['documents'][1]['pages'][0]['status'], 'duplicate_bytes')
        self.assertEqual(report['documents'][2]['pages'][0]['status'], 'print_false')
        self.assertEqual([p['status'] for p in report['documents'][3]['pages']], ['not_selected', 'prepared', 'not_selected'])

    def test_different_byte_alias_requires_reviewed_identity(self):
        docs = [self.document(1), self.document(2, canonical_of='doc-1')]
        with self.assertRaisesRegex(ValueError, 'canonical_reviewed'):
            self.run_job(docs)
        docs[1].update(canonical_reviewed=True, canonical_reason='Synthetic alternate representation checked manually')
        report = self.run_job(docs)
        self.assertEqual(report['prepared_unique_pages'], 1)
        self.assertEqual(report['documents'][1]['pages'][0]['status'], 'canonical_alias')

    def test_only_user_confirmed_prints_skip_and_prepared_remain(self):
        doc = self.document(1)
        self.run_job([doc])
        report = self.run_job([doc], output='prepared-again', printed_ledger=self.root / 'out/print-ledger.json')
        self.assertEqual(report['prepared_unique_pages'], 1)
        ledger = json.loads((self.root / 'out/print-ledger.json').read_text())
        ledger['pages'][0].update(status='printed', confirmed_by='user', confirmation='User reported this sheet printed')
        ledger_path = self.root / 'confirmed.json'
        ledger_path.write_text(json.dumps(ledger), encoding='utf-8')
        report = self.run_job([doc], output='confirmed-run', printed_ledger=ledger_path)
        self.assertEqual(report['status'], 'no_reprint_needed')
        self.assertFalse(list((self.root / 'confirmed-run').glob('*.pdf')))
        self.assertFalse(report['physical_print_verified'])
        ledger['pages'][0]['confirmed_by'] = None
        ledger_path.write_text(json.dumps(ledger), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'confirmed_by'):
            self.run_job([doc], output='bad-run', printed_ledger=ledger_path)

    def test_crop_requires_review_and_never_edits_original(self):
        doc = self.document(1, views={'1': {'crop': [.05, .1, .95, .9]}})
        before = sheets.digest(self.root / doc['path'])
        with self.assertRaisesRegex(ValueError, 'reviewed:true'):
            self.run_job([doc])
        doc['views']['1']['reviewed'] = True
        report = self.run_job([doc])
        self.assertTrue(report['outputs'][0]['placements'][0]['crop_reviewed'])
        self.assertEqual(sheets.digest(self.root / doc['path']), before)

    def test_auto_rotation_improves_tall_itinerary_fit(self):
        path = self.pdf('tall.pdf', size=(250, 1000))
        report = self.run_job([{'id': 'tall', 'path': path.name}], layout='two_up_136')
        self.assertEqual(report['outputs'][0]['placements'][0]['rotation_degrees_counterclockwise'], 90)

    def test_pdf_rotate_flag_normalized_without_clipping(self):
        original = self.pdf('original.pdf')
        writer = PdfWriter()
        writer.add_page(PdfReader(original).pages[0]).rotate(90)
        rotated = self.root / 'rotated.pdf'
        writer.write(rotated)
        report = self.run_job([{'id': 'rotated', 'path': rotated.name, 'views': {'1': {'rotation': 0}}}])
        output = self.root / 'out' / report['outputs'][0]['file']
        self.assertIn('original.pdf-1-RIGHT', PdfReader(output).pages[0].extract_text())

    def test_existing_output_and_bad_section_path_are_refused(self):
        doc = self.document(1)
        self.run_job([doc])
        with self.assertRaises(FileExistsError):
            self.run_job([doc])
        manifest = {'schema_version': 1, 'sections': [{'id': '../escape', 'kind': 'evidence', 'documents': [doc]}]}
        p = self.root / 'unsafe.json'
        p.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'safe filenames'):
            sheets.build(p, self.root / 'new')


if __name__ == '__main__':
    unittest.main()
