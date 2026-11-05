"""Synthetic-only helper checks. No real receipt data or private profiles are used."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from pypdf import PdfReader
from reportlab.pdfgen import canvas

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'assets/package'

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

helper = load_module('generic_receipt_helper', PACKAGE / 'scripts/prepare_receipts.py')
layouts = load_module('generic_layout_helper', PACKAGE / 'scripts/pack_by_layout.py')

class ReceiptHelperTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='reimbursement-synthetic-')
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def pdf(self, name, label):
        path = self.root / name
        page = canvas.Canvas(str(path), pagesize=(420, 595))
        for x, y, suffix in [(12, 570, 'TOP'), (12, 15, 'BOTTOM'), (300, 570, 'RIGHT')]:
            page.drawString(x, y, label + '-' + suffix)
        page.save()
        return path

    def inspect(self, job, name='job.json'):
        path = self.root / name
        path.write_text(json.dumps(job), encoding='utf-8')
        return path, helper.inspect_job(path)[1]

    def basic_job(self, claim_type='reception'):
        invoice = self.pdf('invoice.pdf', 'SYNTHETIC-INVOICE')
        payment = self.pdf('payment.pdf', 'SYNTHETIC-PAYMENT')
        return {
            'schema_version': 1, 'claim_type': claim_type, 'profile': {},
            'claim': {'attachment_count': None},
            'expenses': [{'id': 'expense-1', 'category': 'reception' if claim_type == 'reception' else 'other', 'amount': '88.75', 'evidence_ids': ['invoice', 'payment']}],
            'evidence': [
                {'id': 'invoice', 'path': str(invoice), 'role': 'invoice', 'amount': '88.75'},
                {'id': 'payment', 'path': str(payment), 'role': 'payment', 'amount': '88.75'}
            ]
        }

    def test_four_rows_preserve_whole_pages_once_and_leave_unused_slots(self):
        evidence, hashes = [], {}
        for number in range(5):
            path = self.pdf(f'source-{number}.pdf', f'PAGE-{number}')
            hashes[path] = hashlib.sha256(path.read_bytes()).hexdigest()
            evidence.append({'id': f'doc-{number}', 'path': str(path), 'role': 'invoice', 'print_layout': 'ctrip_1x4'})
        job = {'schema_version': 1, 'claim_type': 'travel', 'profile': {}, 'expenses': [], 'evidence': evidence}
        _, report = self.inspect(job)
        output = self.root / 'four-rows'
        output.mkdir()
        layouts.pack(report, output)
        pack = report['print_pack']
        self.assertEqual(pack['pages'], 2)
        self.assertEqual(pack['cut_pieces'], 5)
        self.assertEqual([p['used_slots'] for p in pack['page_layouts']], [4, 1])
        self.assertEqual([p['blank_slots'] for p in pack['page_layouts']], [0, 3])
        self.assertEqual([p['slot_row'] for p in pack['placements']], [1, 2, 3, 4, 1])
        self.assertEqual(len({(p['evidence_id'], p['source_page']) for p in pack['placements']}), 5)
        for placement in pack['placements']:
            self.assertTrue(placement['content_full'])
            self.assertFalse(placement['split'])
            self.assertEqual(placement['source_crop_box_points'], placement['source_media_box_points'])
            self.assertEqual(placement['piece_mm'], [198, 66])
            left, bottom, right, top = placement['fitted_box_points']
            slot_left, slot_bottom, slot_right, slot_top = placement['slot_bounds_points']
            self.assertTrue(slot_left <= left < right <= slot_right)
            self.assertTrue(slot_bottom <= bottom < top <= slot_top)
        pages = PdfReader(pack['file']).pages
        for number in range(5):
            combined = ''.join(page.extract_text() or '' for page in pages)
            for suffix in ['TOP', 'BOTTOM', 'RIGHT']:
                self.assertEqual(combined.count(f'PAGE-{number}-{suffix}'), 1)
        self.assertTrue(all(hashlib.sha256(path.read_bytes()).hexdigest() == value for path, value in hashes.items()))

    def test_print_false_keeps_amount_hash_and_links_but_skips_placement(self):
        job = self.basic_job()
        job['evidence'][0]['print'] = False
        _, report = self.inspect(job)
        self.assertFalse(report['errors'])
        self.assertEqual(report['claimed_total_rmb'], '88.75')
        self.assertEqual(report['supporting_unique_invoice_total_rmb'], '88.75')
        self.assertEqual(report['source_page_count'], 2)
        self.assertEqual(report['printable_source_page_count'], 1)
        self.assertEqual(report['excluded_evidence_ids'], ['invoice'])
        self.assertEqual(report['expenses'][0]['evidence_ids'], ['invoice', 'payment'])
        self.assertTrue(report['evidence'][0]['sha256'])
        output = self.root / 'selection'
        output.mkdir()
        helper.pack(job, report, output)
        self.assertEqual([p['evidence_id'] for p in report['print_pack']['placements']], ['payment'])

    def test_all_unprinted_returns_no_reprint_needed(self):
        job = self.basic_job()
        for evidence in job['evidence']:
            evidence['print'] = False
        _, report = self.inspect(job)
        output = self.root / 'no-reprint'
        output.mkdir()
        self.assertEqual(report['status'], 'no_reprint_needed')
        self.assertIsNone(helper.pack(job, report, output))
        self.assertFalse(list(output.glob('*.pdf')))
        self.assertEqual(report['document_count'], 2)
        self.assertEqual(report['claimed_total_rmb'], '88.75')

    def test_unprinted_missing_file_still_reports_error(self):
        job = self.basic_job()
        job['evidence'][0].update({'print': False, 'path': str(self.root / 'missing.pdf')})
        _, report = self.inspect(job)
        self.assertEqual(report['status'], 'invalid_input')
        self.assertTrue(any('file missing' in message for message in report['errors']))

    def test_payment_and_invoice_do_not_double_the_claim(self):
        _, report = self.inspect(self.basic_job())
        self.assertEqual(report['claimed_total_rmb'], '88.75')
        self.assertEqual(report['supporting_unique_invoice_total_rmb'], '88.75')
        self.assertEqual(len(report['expenses']), 1)

    def test_expense_uses_supplied_rows_without_threshold(self):
        job = self.basic_job('expense')
        job['expenses'] = [
            {'id': 'expense-a', 'category': 'other', 'amount': '37.80', 'evidence_ids': ['invoice']},
            {'id': 'expense-b', 'category': 'other', 'amount': '12.45', 'evidence_ids': ['payment']}
        ]
        _, report = self.inspect(job)
        self.assertFalse(report['errors'])
        self.assertEqual(report['claimed_total_rmb'], '50.25')
        self.assertEqual(report['supporting_unique_invoice_total_rmb'], '88.75')
        self.assertFalse(any('threshold' in warning.lower() or 'must exceed' in warning.lower() or 'recipient should' in warning.lower() for warning in report['warnings']))
        self.assertEqual(job['profile'], {})

    def test_cli_print_selection_report(self):
        job = self.basic_job()
        for evidence in job['evidence']:
            evidence['print'] = False
        job_path, _ = self.inspect(job)
        output = self.root / 'cli'
        result = subprocess.run([sys.executable, str(PACKAGE / 'scripts/pack_by_layout.py'), '--job', str(job_path), '--output', str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])
        report = json.loads((output / 'processing-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'no_reprint_needed')
        self.assertFalse(list(output.glob('*.pdf')))

    def test_form_filler_expense_and_blank_profile_when_runtime_available(self):
        master = PACKAGE / 'forms/reimbursement-forms.xlsx'
        if not master.is_file():
            self.skipTest('Generic workbook is not available')
        node = shutil.which('node')
        if not node:
            candidate = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin' / ('node.exe' if os.name == 'nt' else 'node')
            node = str(candidate) if candidate.is_file() else None
        if not node:
            self.skipTest('Node runtime is not available')
        job = self.basic_job('expense')
        job['expenses'] = [
            {'id': 'expense-a', 'category': 'other', 'amount': '37.80', 'evidence_ids': ['invoice']},
            {'id': 'expense-b', 'category': 'other', 'amount': '12.45', 'evidence_ids': ['payment']}
        ]
        job_path, _ = self.inspect(job)
        output = self.root / 'filled'
        result = subprocess.run([node, str(PACKAGE / 'forms/fill_forms.mjs'), '--job', str(job_path), '--output', str(output)], capture_output=True, text=True, encoding='utf-8')
        if result.returncode and 'artifact-tool is required' in result.stderr:
            self.skipTest('Codex spreadsheet dependency is not available')
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])
        report = json.loads((output / 'filled-form-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['claimed_total_rmb'], 50.25)
        self.assertEqual(report['expense_rows_written'], 2)
        self.assertEqual(report['print_sheets'], ['费用报销单'])
        with ZipFile(report['output']) as archive:
            namespace = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            shared = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                strings = ET.fromstring(archive.read('xl/sharedStrings.xml'))
                shared = [''.join(item.itertext()) for item in strings.findall('s:si', namespace)]
            guide = ET.fromstring(archive.read('xl/worksheets/sheet4.xml'))
            cells = {cell.attrib['r']: cell for cell in guide.findall('.//s:c', namespace)}
            for ref in ['B4', 'B5', 'B6', 'B7', 'B8', 'B9']:
                cell = cells.get(ref)
                if cell is not None:
                    value = cell.find('s:v', namespace)
                    content = value.text if value is not None else ''
                    if cell.attrib.get('t') == 's' and content:
                        content = shared[int(content)]
                    elif cell.attrib.get('t') == 'inlineStr':
                        content = ''.join(cell.find('s:is', namespace).itertext())
                    self.assertFalse((content or '').strip(), f'Unexpected profile default in {ref}')

if __name__ == '__main__':
    unittest.main()
