"""Whole-page receipt packing with optional evidence.print_layout='ctrip_1x4'."""
from pathlib import Path
import argparse, hashlib, importlib.util, io, json, sys
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.pdfgen import canvas

sys.dont_write_bytecode = True
BASE_HELPER = Path(__file__).resolve().with_name('prepare_receipts.py')
spec = importlib.util.spec_from_file_location('frozen_receipt_helper', BASE_HELPER)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
MM = base.MM

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def layout_for(item):
    override = item.get('print_layout')
    if override == 'ctrip_1x4':
        return {'name': 'ctrip_1x4', 'columns': 1, 'rows': 4, 'piece_mm': [198, 66], 'gap_mm': 4}
    if override not in {None, ''}:
        raise ValueError(f"Unsupported print_layout for {item['id']}: {override}")
    columns, rows, piece = base.grid_for(item['role'])
    return {'name': 'payment_2x2' if item['role'] == 'payment' else 'ordinary_1x2', 'columns': columns, 'rows': rows, 'piece_mm': list(piece), 'gap_mm': 4}

def positions(layout):
    columns, rows = layout['columns'], layout['rows']
    width, height = (v * MM for v in layout['piece_mm'])
    gap = layout['gap_mm'] * MM
    left = (base.A4[0] - columns * width - (columns - 1) * gap) / 2
    bottom = (base.A4[1] - rows * height - (rows - 1) * gap) / 2
    assert left >= 5 * MM and bottom >= 5 * MM
    return [(left + c * (width + gap), bottom + (rows - 1 - r) * (height + gap), width, height, r + 1, c + 1) for r in range(rows) for c in range(columns)]

def cut_guides(page, boxes):
    buffer = io.BytesIO()
    drawing = canvas.Canvas(buffer, pagesize=base.A4)
    drawing.setStrokeColorRGB(.68, .68, .68)
    drawing.setLineWidth(.3)
    drawing.setDash(2, 2)
    for x, y, width, height, _, _ in boxes:
        drawing.rect(x, y, width, height)
    drawing.showPage()
    drawing.save()
    page.merge_page(PdfReader(io.BytesIO(buffer.getvalue())).pages[0])

def pack(report, output):
    if report['evidence'] and report['printable_source_page_count'] == 0:
        report['status'] = 'no_reprint_needed'
        return
    writer = PdfWriter()
    placements, page_records = [], []
    current_key, destination, slots, used = None, None, [], 0
    for item in report['evidence']:
        if not item.get('print', True):
            continue
        layout = layout_for(item)
        key = (layout['name'], tuple(layout['piece_mm']), layout['rows'], layout['columns'])
        for source_index, source_page in enumerate(base.source_pages(item), 1):
            if destination is None or current_key != key or used == len(slots):
                destination = writer.add_blank_page(*base.A4)
                slots = positions(layout)
                used = 0
                current_key = key
                page_records.append({'output_page': len(writer.pages), 'layout': layout, 'capacity': len(slots), 'used_slots': 0})
                if layout['name'] == 'ctrip_1x4':
                    cut_guides(destination, slots)
            x, y, width, height, row, column = slots[used]
            used += 1
            box = source_page.cropbox
            source_box = [float(v) for v in box]
            media_box = [float(v) for v in source_page.mediabox]
            if layout['name'] == 'ctrip_1x4':
                assert all(abs(a - b) < .001 for a, b in zip(source_box, media_box)), 'Ctrip source is not a full uncropped page'
            source_width, source_height = float(box.width), float(box.height)
            if source_width <= 0 or source_height <= 0:
                raise ValueError(f"Invalid source page bounds: {item['id']}")
            padding = 2 * MM
            scale = min((width - 2 * padding) / source_width, (height - 2 * padding) / source_height)
            fitted_width, fitted_height = source_width * scale, source_height * scale
            fitted_x, fitted_y = x + (width - fitted_width) / 2, y + (height - fitted_height) / 2
            transform = Transformation().translate(-source_box[0], -source_box[1]).scale(scale).translate(fitted_x, fitted_y)
            destination.merge_transformed_page(source_page, transform, expand=False)
            if layout['name'] != 'ctrip_1x4':
                cut_guides(destination, [slots[used - 1]])
            assert fitted_x >= x and fitted_y >= y
            assert fitted_x + fitted_width <= x + width + .001 and fitted_y + fitted_height <= y + height + .001
            source_path = item.get('original_evidence_path', item['resolved_path'])
            placements.append({
                'evidence_id': item['id'], 'source_id': item.get('source_id'),
                'source_page': source_index, 'output_page': len(writer.pages),
                'print_layout': layout['name'], 'slot_row': row, 'slot_column': column,
                'slot_bounds_points': [x, y, x + width, y + height],
                'slot_bounds_mm': [v / MM for v in [x, y, x + width, y + height]],
                'piece_mm': layout['piece_mm'],
                'fitted_box_points': [fitted_x, fitted_y, fitted_x + fitted_width, fitted_y + fitted_height],
                'fitted_box_mm': [v / MM for v in [fitted_x, fitted_y, fitted_x + fitted_width, fitted_y + fitted_height]],
                'source_box_points': source_box, 'scale': scale,
                'source_crop_box_points': source_box, 'source_media_box_points': media_box,
                'transform_matrix': list(transform.ctm),
                'aspect_ratio_preserved': True, 'content_full': True, 'split': False,
                'source_crop_box_unmodified': True,
                'source_path': source_path, 'source_sha256': item.get('original_sha256', item['sha256']),
                'print_source_path': item['resolved_path'], 'print_source_sha256': item['sha256'],
                'print_derivative_provenance': item.get('print_derivative_provenance'),
            })
            page_records[-1]['used_slots'] += 1
    if not placements:
        raise ValueError('No readable printable evidence pages')
    assert len(placements) == report['printable_source_page_count'], 'Printable page conservation failed'
    assert len({(p['evidence_id'], p['source_page']) for p in placements}) == len(placements), 'A page was repeated'
    for page in page_records:
        page['blank_slots'] = page['capacity'] - page['used_slots']
    target = output / ('attachments-4up-a4.pdf' if any(p['print_layout'] == 'ctrip_1x4' for p in placements) else 'attachments-a4.pdf')
    if target.exists():
        raise FileExistsError(f'Output exists: {target}')
    writer.write(str(target))
    assert len(PdfReader(str(target)).pages) == len(page_records)
    report['print_pack'] = {'file': str(target), 'sha256': digest(target), 'pages': len(writer.pages), 'cut_pieces': len(placements), 'placements': placements, 'page_layouts': page_records, 'print_scale': '100%; do not fit or shrink', 'page_size_mm': [210, 297], 'source_pages_conserved': True, 'ctrip_whole_pages_only': True, 'ctrip_splitting': False, 'ctrip_crop_or_stretch': False, 'physical_print_verified': False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    report_path = output / 'processing-report.json'
    if report_path.exists():
        raise FileExistsError(f'Choose a new output directory: {report_path}')
    output.mkdir(parents=True, exist_ok=True)
    job, report = base.inspect_job(args.job)
    report['job_path'] = str(Path(args.job).resolve())
    report['job_sha256'] = digest(args.job)
    report['layout_override_contract'] = "evidence.print_layout='ctrip_1x4': whole original page per198x66mm strip, one column/four rows; default layouts otherwise"
    if not report['errors']:
        try:
            pack(report, output)
        except Exception as exc:
            report['errors'].append(str(exc))
            report['status'] = 'invalid_input'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'errors': report['errors'], 'pages': report.get('print_pack', {}).get('pages'), 'report': str(report_path)}, ensure_ascii=False))
    return 1 if report['errors'] else 0

if __name__ == '__main__':
    sys.exit(main())
