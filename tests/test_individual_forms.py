"""Synthetic regression cases for person-only notes and retained leg fees."""
from pathlib import Path
from zipfile import ZipFile
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'assets/package'
spec = importlib.util.spec_from_file_location('individual_receipts', PACKAGE / 'scripts/prepare_receipts.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


class IndividualFormTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='individual-form-synthetic-')
        self.root = Path(self.temp.name)
        from reportlab.pdfgen import canvas
        for name in ('fare', 'fee'):
            pdf = canvas.Canvas(str(self.root / (name + '.pdf')))
            pdf.drawString(30, 700, 'SYNTHETIC ' + name)
            pdf.save()
        self.job = {
            'schema_version': 1, 'claim_type': 'travel', 'profile': {},
            'claim': {'subject_name': 'SYNTHETIC TRAVELER', 'single_traveler': True},
            'expenses': [
                {'id': 'outbound', 'category': 'flight', 'amount': '100.25',
                 'other_amount': '3.50', 'other_evidence_ids': ['fee'],
                 'date': '2025-01-02', 'purpose': '出差机票', 'origin': 'A', 'destination': 'B',
                 'ticket_count': 1, 'evidence_ids': ['fare', 'fee']},
                {'id': 'return', 'category': 'flight', 'amount': '50.00',
                 'date': '2025-01-05', 'purpose': '出差机票', 'origin': 'B', 'destination': 'A',
                 'ticket_count': 1, 'evidence_ids': ['fare']},
            ],
            'evidence': [
                {'id': 'fare', 'role': 'invoice', 'path': 'fare.pdf', 'amount': '150.25'},
                {'id': 'fee', 'role': 'invoice', 'path': 'fee.pdf', 'amount': '3.50'},
            ],
        }

    def tearDown(self):
        self.temp.cleanup()

    def inspect(self, job):
        path = self.root / 'job.json'
        path.write_text(json.dumps(job), encoding='utf-8')
        return path, helper.inspect_job(path)[1]

    def node(self):
        runtime = shutil.which('node')
        if not runtime:
            candidate = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin' / ('node.exe' if os.name == 'nt' else 'node')
            runtime = str(candidate) if candidate.is_file() else None
        if not runtime:
            self.skipTest('Node runtime unavailable')
        return runtime

    def fill(self, job, directory):
        path, _ = self.inspect(job)
        result = subprocess.run([self.node(), str(PACKAGE / 'forms/fill_forms.mjs'), '--job', str(path), '--output', str(self.root / directory)], capture_output=True, text=True, encoding='utf-8')
        if result.returncode and 'artifact-tool is required' in result.stderr:
            self.skipTest('Codex spreadsheet dependency unavailable')
        return result

    def cells(self, path, sheet):
        with ZipFile(path) as archive:
            shared = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                shared = [''.join(s.itertext()) for s in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('m:si', NS)]
            tree = ET.fromstring(archive.read(f'xl/worksheets/sheet{sheet}.xml'))
            result = {}
            for cell in tree.findall('.//m:c', NS):
                value = cell.find('m:v', NS)
                content = value.text if value is not None else ''
                if cell.attrib.get('t') == 's' and content:
                    content = shared[int(content)]
                elif cell.attrib.get('t') == 'inlineStr':
                    content = ''.join(cell.find('m:is', NS).itertext())
                result[cell.attrib['r']] = content
            return result

    def test_checker_adds_linked_fee_once_and_keeps_two_legs(self):
        _, report = self.inspect(self.job)
        self.assertFalse(report['errors'])
        self.assertEqual(report['claimed_total_rmb'], '153.75')
        self.assertEqual(report['ancillary_total_rmb'], '3.50')
        self.assertEqual(len(report['expenses']), 2)

    def test_checker_rejects_duplicate_fee_invalid_amount_and_wrong_count(self):
        cases = []
        job = copy.deepcopy(self.job)
        job['expenses'].append({'id': 'duplicate-fee', 'category': 'other', 'amount': '3.50', 'evidence_ids': ['fee']})
        cases.append((job, 'already claimed'))
        for value in ['-1.00', '1.001', '']:
            job = copy.deepcopy(self.job)
            job['expenses'][0]['other_amount'] = value
            cases.append((job, 'other_amount'))
        job = copy.deepcopy(self.job)
        job['expenses'][0]['ticket_count'] = 2
        cases.append((job, 'ticket_count 1'))
        job = copy.deepcopy(self.job)
        del job['expenses'][0]['other_evidence_ids']
        cases.append((job, 'other_evidence_ids'))
        for job, expected in cases:
            with self.subTest(expected=expected):
                _, report = self.inspect(job)
                self.assertTrue(any(expected in e for e in report['errors']), report['errors'])

    def test_filler_puts_fee_on_same_leg_and_name_only_when_runtime_available(self):
        master = PACKAGE / 'forms/reimbursement-forms.xlsx'
        before = hashlib.sha256(master.read_bytes()).hexdigest()
        result = self.fill(self.job, 'travel')
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])
        report = json.loads((self.root / 'travel/filled-form-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['claimed_total_rmb'], 153.75)
        self.assertEqual(report['expense_rows_written'], 2)
        self.assertEqual(report['remarks_mode'], 'subject_name_only')
        cells = self.cells(report['output'], 2)
        self.assertEqual(cells['K1'], 'SYNTHETIC TRAVELER')
        self.assertEqual(cells['C7'], '出差机票')
        self.assertEqual(float(cells['F7']), 1)
        self.assertEqual(float(cells['G7']), 100.25)
        self.assertEqual(float(cells['N7']), 3.50)
        self.assertEqual(float(cells['O7']), 103.75)
        self.assertEqual(float(cells['O13']), 153.75)
        self.assertFalse(cells.get('N8'))
        guide = self.cells(report['output'], 4)
        for key in ['B5', 'B6', 'B7', 'B8']:
            self.assertFalse(guide.get(key))
        self.assertEqual(hashlib.sha256(master.read_bytes()).hexdigest(), before)

    def test_filler_expense_name_is_not_recipient_when_runtime_available(self):
        job = copy.deepcopy(self.job)
        job['claim_type'] = 'expense'
        job['claim'] = {'subject_name': 'SYNTHETIC SUBJECT'}
        job['profile'] = {'recipient': 'SYNTHETIC DIFFERENT RECIPIENT'}
        job['expenses'] = [{'id': 'cost', 'category': 'other', 'amount': '30.00', 'evidence_ids': ['fare']}]
        result = self.fill(job, 'expense')
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])
        report = json.loads((self.root / 'expense/filled-form-report.json').read_text(encoding='utf-8'))
        self.assertEqual(self.cells(report['output'], 1)['T1'], 'SYNTHETIC SUBJECT')
        self.assertEqual(self.cells(report['output'], 4)['B6'], 'SYNTHETIC DIFFERENT RECIPIENT')

    def test_filler_rejects_double_claim_before_export(self):
        job = copy.deepcopy(self.job)
        job['expenses'].append({'id': 'duplicate-fee', 'category': 'other', 'amount': '3.50', 'evidence_ids': ['fee']})
        result = self.fill(job, 'invalid')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('already claimed', result.stderr)
        self.assertFalse((self.root / 'invalid').exists())


if __name__ == '__main__':
    unittest.main()
