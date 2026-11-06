"""Local evidence checks/A4 packing; print=False retains evidence without reprinting it."""
from pathlib import Path
from decimal import Decimal, InvalidOperation
import argparse, hashlib, io, json, sys
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

MM = 72 / 25.4
A4 = (210 * MM, 297 * MM)
ROLES = {'invoice', 'payment', 'bill', 'itinerary', 'approval', 'other'}
CLAIMS = {'travel', 'reception', 'expense'}
FORM_CATEGORIES = {
    'flight': '车船票', 'rail': '车船票', 'taxi': '交通费',
    'meal': '餐费', 'hotel': '住宿费', 'other': '其他',
    'reception': '招待费用'
}

def money(value, label, errors):
    if value is None or value == '':
        return None
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d < 0 or d != d.quantize(Decimal('.01')):
            raise ValueError()
        return d
    except (InvalidOperation, ValueError):
        errors.append(f'{label}: expected a nonnegative RMB amount with at most two decimal places')
        return None

def inspect_job(job_path):
    job_path = Path(job_path).resolve()
    job = json.loads(job_path.read_text(encoding='utf-8-sig'))
    errors, warnings = [], []
    claim_type = job.get('claim_type')
    if claim_type not in CLAIMS:
        errors.append('claim_type must be travel, reception or expense')
    profile = job.get('profile', {})
    claim = job.get('claim', {})
    subject = claim.get('subject_name')
    if 'subject_name' in claim and (not isinstance(subject, str) or '\n' in subject or '\r' in subject):
        errors.append('claim.subject_name must be a single-line name string')
    if 'single_traveler' in claim and type(claim['single_traveler']) is not bool:
        errors.append('claim.single_traveler must be boolean')
    if claim.get('single_traveler') and (claim_type != 'travel' or not isinstance(subject, str) or not subject.strip()):
        errors.append('single_traveler requires a travel claim and explicit subject_name')
    expenses = job.get('expenses', [])
    evidence = job.get('evidence', [])
    ids = [e.get('id') for e in expenses]
    if any(not v for v in ids) or len(ids) != len(set(ids)):
        errors.append('Expense ids must be nonempty and unique')
    evids = [e.get('id') for e in evidence]
    if any(not v for v in evids) or len(evids) != len(set(evids)):
        errors.append('Evidence ids must be nonempty and unique')
    if not expenses:
        warnings.append('No expense lines supplied; this is an incomplete draft')
    claimed_total = Decimal('0')
    missing_amount = False
    prepared_expenses = []
    ancillary_evidence = {}
    ancillary_total = Decimal('0')
    for e in expenses:
        category = e.get('category')
        if category not in FORM_CATEGORIES:
            errors.append(f"Expense {e.get('id')}: unsupported category {category}")
        amount = money(e.get('amount'), f"Expense {e.get('id')}", errors)
        missing_amount |= amount is None
        if amount is not None:
            claimed_total += amount
        if claim.get('single_traveler') and category == 'flight' and (type(e.get('ticket_count')) is not int or e['ticket_count'] != 1):
            errors.append(f"Expense {e.get('id')}: individual flight leg requires ticket_count 1")
        other_amount = Decimal('0')
        if e.get('other_amount') is not None:
            if claim_type != 'travel' or category not in {'flight', 'rail'}:
                errors.append(f"Expense {e.get('id')}: other_amount is allowed only on a travel flight/rail leg")
            other_amount = money(e['other_amount'], f"Expense {e.get('id')} other_amount", errors)
            missing_amount |= other_amount is None
            if other_amount is None and e['other_amount'] == '':
                errors.append(f"Expense {e.get('id')}: other_amount cannot be empty")
            if other_amount is not None:
                claimed_total += other_amount
                ancillary_total += other_amount
            if other_amount is not None and other_amount > 0:
                extra_links = e.get('other_evidence_ids')
                if (not isinstance(extra_links, list) or not extra_links or
                        any(not isinstance(v, str) for v in extra_links) or
                        len(set(extra_links)) != len(extra_links) or
                        not set(extra_links) <= set(e.get('evidence_ids', []))):
                    errors.append(f"Expense {e.get('id')}: positive other_amount requires unique other_evidence_ids included in evidence_ids")
                else:
                    for extra_id in extra_links:
                        if extra_id in ancillary_evidence:
                            errors.append(f'Ancillary evidence {extra_id} is claimed on multiple legs')
                        ancillary_evidence[extra_id] = e.get('id')
        links = e.get('evidence_ids', [])
        if not set(links) <= set(evids):
            errors.append(f"Expense {e.get('id')}: unknown linked evidence id")
        linked = [v for v in evidence if v.get('id') in links]
        if category in {'flight', 'taxi', 'meal', 'reception'} and not any(v.get('role') == 'payment' for v in linked):
            warnings.append(f"Expense {e.get('id')}: payment evidence missing")
        if category == 'taxi' and not any(v.get('role') == 'itinerary' for v in linked):
            warnings.append(f"Expense {e.get('id')}: taxi itinerary/start-end evidence missing")
        prepared_expenses.append({**e, 'form_category': FORM_CATEGORIES.get(category), 'amount': str(amount) if amount is not None else None,
                                  'other_amount': str(other_amount) if other_amount is not None else None})
    for e in expenses:
        if e.get('category') != 'other':
            continue
        for linked_id in e.get('evidence_ids', []):
            if linked_id in ancillary_evidence and ancillary_evidence[linked_id] != e.get('id'):
                errors.append(f"Expense {e.get('id')}: ancillary evidence {linked_id} is already claimed on its linked leg; remove the duplicate claim")
    files, hashes = [], {}
    invoice_values = {}
    for e in evidence:
        label = str(e.get('id'))
        if e.get('role') not in ROLES:
            errors.append(f'Evidence {label}: unsupported role')
        should_print = e.get('print', True)
        if not isinstance(should_print, bool):
            errors.append(f'Evidence {label}: print must be true or false')
            should_print = True
        raw_path = e.get('path', '')
        if not raw_path:
            errors.append(f'Evidence {label}: path missing')
            continue
        p = Path(raw_path)
        p = (job_path.parent / p).resolve() if not p.is_absolute() else p.resolve()
        if not p.is_file():
            errors.append(f'Evidence {label}: file missing: {p}')
            continue
        if p.suffix.lower() not in {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
            errors.append(f'Evidence {label}: unsupported format {p.suffix}; convert explicitly, do not skip')
            continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        duplicate_of = hashes.get(digest)
        if duplicate_of:
            warnings.append(f'Evidence {label}: same bytes as {duplicate_of}; review duplicate, no automatic deletion')
        else:
            hashes[digest] = label
        amount = money(e.get('amount'), f'Evidence {label}', errors)
        if e.get('role') == 'invoice':
            invoice_values.setdefault(digest, set()).add(amount)
        try:
            pages = len(PdfReader(str(p)).pages) if p.suffix.lower() == '.pdf' else 1
        except Exception as exc:
            errors.append(f'Evidence {label}: cannot read document ({type(exc).__name__})')
            continue
        files.append({**e, 'print': should_print, 'resolved_path': str(p), 'sha256': digest, 'duplicate_of': duplicate_of, 'page_count': pages})
    invoice_total = Decimal('0')
    unknown_invoice_amounts = 0
    for digest, values in invoice_values.items():
        if None in values or len(values) != 1:
            unknown_invoice_amounts += 1
            if len(values) > 1:
                warnings.append(f'Conflicting invoice amounts for source hash {digest}; exclude from supporting total until reviewed')
        else:
            invoice_total += next(iter(values))
    if not evidence:
        warnings.append('No evidence supplied')
    if claim_type == 'travel' and not any(e.get('role') == 'approval' for e in evidence):
        warnings.append('No travel approval evidence supplied; attach it only if your reimbursement process requires it')
    if missing_amount:
        warnings.append('Some expense amounts are missing; total is incomplete')
    if not profile.get('bank') or not profile.get('account'):
        warnings.append('Bank/account not supplied; keep printable fields blank')
    printable_page_count = sum(f['page_count'] for f in files if f['print'])
    excluded_ids = [f['id'] for f in files if not f['print']]
    status = 'invalid_input' if errors else 'no_reprint_needed' if files and printable_page_count == 0 else 'needs_review'
    report = {
        'schema_version': 1, 'claim_type': claim_type,
        'status': status,
        'claimed_total_rmb': str(claimed_total.quantize(Decimal('.01'))),
        'ancillary_total_rmb': str(ancillary_total.quantize(Decimal('.01'))),
        'claimed_total_complete': bool(expenses) and not missing_amount,
        'supporting_unique_invoice_total_rmb': str(invoice_total.quantize(Decimal('.01'))),
        'unknown_invoice_amounts': unknown_invoice_amounts,
        'document_count': len(files), 'source_page_count': sum(f['page_count'] for f in files),
        'printable_source_page_count': printable_page_count,
        'excluded_evidence_ids': excluded_ids, 'excluded_evidence_count': len(excluded_ids),
        'printable_attachment_count': None,
        'cover_mm': {'width': 220, 'height': 136},
        'signatures': 'blank', 'errors': errors, 'warnings': warnings,
        'expenses': prepared_expenses, 'evidence': files,
        'source_companions': job.get('source_companions', []),
        'no_ocr_or_external_upload': True,
        'limits': 'Amounts are supplied inputs, not verified OCR. Invoice/payment evidence never creates a second expense. print=false keeps files in evidence/hash/amount checks but excludes packing only. Source companions are metadata, not printable evidence or a second invoice amount; their contents are not parsed by this helper. Counts are diagnostics; the form attachment-count field stays blank.'
    }
    return job, report

def source_pages(item):
    p = Path(item['resolved_path'])
    if p.suffix.lower() == '.pdf':
        reader = PdfReader(str(p))
        for page in reader.pages:
            if page.rotation:
                page.transfer_rotation_to_content()
            yield page
    else:
        with Image.open(p) as original:
            img = ImageOps.exif_transpose(original).convert('RGB')
            width, height = img.size
            buffer = io.BytesIO()
            doc = canvas.Canvas(buffer, pagesize=(width, height))
            doc.drawImage(ImageReader(img), 0, 0, width=width, height=height)
            doc.showPage()
            doc.save()
            yield PdfReader(io.BytesIO(buffer.getvalue())).pages[0]

def slots(columns, rows, piece_mm):
    width, height = piece_mm[0] * MM, piece_mm[1] * MM
    gap = 4 * MM
    left = (A4[0] - (columns * width + (columns - 1) * gap)) / 2
    bottom = (A4[1] - (rows * height + (rows - 1) * gap)) / 2
    assert left >= 5 * MM and bottom >= 5 * MM
    for r in range(rows):
        for c in range(columns):
            yield (left + c * (width + gap), bottom + (rows - 1 - r) * (height + gap), width, height)

def grid_for(role):
    # Cut pieces stay strictly inside the measured 220 x 136 mm cover.
    return (2, 2, (96, 126)) if role == 'payment' else (1, 2, (198, 126))

def pack(job, report, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if report['evidence'] and report['printable_source_page_count'] == 0:
        report['status'] = 'no_reprint_needed'
        return None
    writer = PdfWriter()
    placements = []
    # Keep supplied document order. Change packing only at role transitions.
    group_key, dest, positions, used = None, None, [], 0
    for item in report['evidence']:
        if not item.get('print', True):
            continue
        key = grid_for(item['role'])
        for index, page in enumerate(source_pages(item), 1):
            if key != group_key or dest is None or used == len(positions):
                dest = writer.add_blank_page(*A4)
                positions = list(slots(*key))
                used = 0
                group_key = key
            sx, sy, sw, sh = positions[used]
            used += 1
            box = page.cropbox
            source_w, source_h = float(box.width), float(box.height)
            if source_w <= 0 or source_h <= 0:
                raise ValueError(f"Invalid page bounds: {item['id']}")
            padding = 2 * MM
            factor = min((sw - 2 * padding) / source_w, (sh - 2 * padding) / source_h)
            tx = sx + (sw - source_w * factor) / 2
            ty = sy + (sh - source_h * factor) / 2
            transform = Transformation().translate(-float(box.left), -float(box.bottom)).scale(factor).translate(tx, ty)
            dest.merge_transformed_page(page, transform, expand=False)
            # Cut guides are outside content; source page remains complete and uncropped.
            overlay = io.BytesIO()
            guide = canvas.Canvas(overlay, pagesize=A4)
            guide.setStrokeColorRGB(.68, .68, .68)
            guide.setLineWidth(.3)
            guide.setDash(2, 2)
            guide.rect(sx, sy, sw, sh)
            guide.showPage(); guide.save()
            dest.merge_page(PdfReader(io.BytesIO(overlay.getvalue())).pages[0])
            placements.append({'evidence_id': item['id'], 'source_page': index, 'output_page': len(writer.pages), 'piece_mm': list(key[2]), 'source_crop_preserved': True})
    if not placements:
        raise ValueError('No readable evidence pages to pack')
    target = output / 'attachments-a4.pdf'
    writer.write(str(target))
    report['print_pack'] = {'file': str(target), 'pages': len(writer.pages), 'cut_pieces': len(placements), 'placements': placements, 'print_scale': '100%; do not fit or shrink', 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    assert len(placements) == report['printable_source_page_count'], 'A printable source page was omitted'
    return target

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    job, report = inspect_job(args.job)
    output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=True)
    if not report['errors'] and not args.check_only:
        try:
            pack(job, report, output)
        except Exception as exc:
            report['errors'].append(str(exc))
            report['status'] = 'invalid_input'
    (output / 'processing-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'errors': report['errors'], 'warnings': report['warnings'], 'source_pages': report['source_page_count'], 'printable_source_pages': report['printable_source_page_count'], 'excluded_evidence_ids': report['excluded_evidence_ids'], 'output': str(output)}, ensure_ascii=False))
    return 1 if report['errors'] else 0

if __name__ == '__main__':
    sys.exit(main())
