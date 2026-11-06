"""Pack reviewed PDFs/images into separate A4 print sheets with shared cut lines.

This helper lays out supplied evidence. It does not classify expenses, infer payers,
OCR documents, validate financial eligibility, or operate a printer.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import math
import re
import sys

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

MM = 72 / 25.4
LAYOUTS = {'grid_2x2', 'two_up_136', 'strips_1x4'}
FORMATS = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.bmp'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f'{label}: expected a finite number')
    return float(value)


def geometry(layout, orientation='portrait', margin_mm=6):
    """Return bottom-left PDF coordinates; stock edges are final piece edges."""
    if layout not in LAYOUTS or orientation not in {'portrait', 'landscape'}:
        raise ValueError('Unsupported layout or orientation')
    if layout == 'two_up_136' and orientation != 'portrait':
        raise ValueError('two_up_136 requires portrait A4')
    margin = finite(margin_mm, 'margin_mm')
    if not 2 <= margin <= 15:
        raise ValueError('margin_mm must be between 2 and 15')
    width, height = (210, 297) if orientation == 'portrait' else (297, 210)
    if layout == 'grid_2x2':
        slots = [(col * width / 2, height - (row + 1) * height / 2,
                  width / 2, height / 2) for row in range(2) for col in range(2)]
        guides = [(width / 2, 0, width / 2, height), (0, height / 2, width, height / 2)]
    elif layout == 'two_up_136':
        slots = [(0, height - (row + 1) * 136, width, 136) for row in range(2)]
        guides = [(0, height - 136, width, height - 136), (0, height - 272, width, height - 272)]
    else:
        slots = [(0, height - (row + 1) * height / 4, width, height / 4) for row in range(4)]
        guides = [(0, height - row * height / 4, width, height - row * height / 4) for row in range(1, 4)]
    return {'page_mm': [width, height], 'slots_mm': slots, 'guides_mm': guides, 'margin_mm': margin}


def source_pages(path):
    if path.suffix.lower() == '.pdf':
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ValueError(f'Encrypted PDF is not supported: {path.name}')
        # Own the pages before normalizing /Rotate so pypdf need not mutate a
        # reader-owned content stream. No bytes are written back to the source.
        owner = PdfWriter()
        pages = [owner.add_page(page) for page in reader.pages]
        for page in pages:
            if page.rotation:
                page.transfer_rotation_to_content()
        return pages
    with Image.open(path) as original:
        if getattr(original, 'n_frames', 1) != 1:
            raise ValueError(f'Multi-frame image requires explicit page conversion: {path.name}')
        img = ImageOps.exif_transpose(original).convert('RGBA')
        background = Image.new('RGBA', img.size, 'white')
        background.alpha_composite(img)
        rgb = background.convert('RGB')
        output = io.BytesIO()
        drawing = canvas.Canvas(output, pagesize=rgb.size)
        drawing.drawImage(ImageReader(rgb), 0, 0, width=rgb.width, height=rgb.height)
        drawing.save()
    return list(PdfReader(io.BytesIO(output.getvalue())).pages)


def load_printed(path):
    """Only explicitly confirmed physical print records can suppress pages."""
    if path is None:
        return set()
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    records = data.get('pages')
    if data.get('schema_version') != 1 or not isinstance(records, list):
        raise ValueError('Printed ledger requires schema_version 1 and pages array')
    printed = set()
    for record in records:
        if record.get('status') != 'printed':
            continue
        if record.get('confirmed_by') != 'user' or not isinstance(record.get('confirmation'), str) or not record['confirmation'].strip():
            raise ValueError('A printed ledger entry requires confirmed_by:user and user confirmation text')
        sha = record.get('sha256', '')
        page = record.get('page')
        if not re.fullmatch('[0-9a-f]{64}', sha) or type(page) is not int or page < 1:
            raise ValueError('Invalid printed page identity')
        printed.add((sha, page))
    return printed


def view_for(doc, page_number, page):
    views = doc.get('views', {})
    view = views.get(str(page_number), {})
    if not isinstance(view, dict):
        raise ValueError(f"{doc['id']}: page view must be an object")
    crop = view.get('crop', [0, 0, 1, 1])
    if not isinstance(crop, list) or len(crop) != 4:
        raise ValueError(f"{doc['id']}: crop requires four normalized coordinates")
    left, top, right, bottom = [finite(v, 'crop') for v in crop]
    if not 0 <= left < right <= 1 or not 0 <= top < bottom <= 1:
        raise ValueError(f"{doc['id']}: invalid normalized crop")
    if crop != [0, 0, 1, 1] and view.get('reviewed') is not True:
        raise ValueError(f"{doc['id']}: cropping requires reviewed:true after checking the source")
    rotation = view.get('rotation', 'auto')
    if rotation not in {'auto', 0, 90} or isinstance(rotation, bool):
        raise ValueError(f"{doc['id']}: rotation must be auto, 0 or 90")
    box = page.cropbox
    x0, y0, x1, y1 = map(float, box)
    return {
        'crop_normalized': crop,
        'crop_box_points': [x0 + left * (x1 - x0), y1 - bottom * (y1 - y0),
                            x0 + right * (x1 - x0), y1 - top * (y1 - y0)],
        'original_crop_box_points': [x0, y0, x1, y1],
        'rotation': rotation,
        'crop_reviewed': view.get('reviewed', False),
    }


def inspect_manifest(manifest_path, printed_ledger=None):
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    if manifest.get('schema_version') != 1 or not isinstance(manifest.get('sections'), list):
        raise ValueError('Manifest requires schema_version 1 and sections array')
    printed = load_printed(printed_ledger)
    sections, records, ids, section_ids = [], [], {}, set()
    seen_pages = {}
    for section in manifest['sections']:
        section_id = section.get('id', '')
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', section_id) or section_id in section_ids:
            raise ValueError('Section IDs must be unique safe filenames')
        section_ids.add(section_id)
        if section.get('kind') not in {'forms', 'evidence'}:
            raise ValueError(f'{section_id}: kind must be forms or evidence')
        layout = section.get('layout', 'grid_2x2')
        orientation = section.get('orientation', 'landscape' if layout == 'grid_2x2' else 'portrait')
        geo = geometry(layout, orientation, section.get('margin_mm', 6))
        documents = section.get('documents')
        if not isinstance(documents, list):
            raise ValueError(f'{section_id}: documents must be an array')
        prepared, declared_pairs = [], {}
        for doc in documents:
            doc_id = doc.get('id')
            if not isinstance(doc_id, str) or not doc_id.strip() or doc_id in ids:
                raise ValueError('Document IDs must be nonempty and globally unique')
            raw_path = doc.get('path')
            if not isinstance(raw_path, str) or not raw_path:
                raise ValueError(f'{doc_id}: path required')
            source = Path(raw_path)
            source = (path.parent / source).resolve() if not source.is_absolute() else source.resolve()
            if not source.is_file() or source.suffix.lower() not in FORMATS:
                raise ValueError(f'{doc_id}: missing or unsupported source file')
            sha = digest(source)
            pages = source_pages(source)
            if not pages:
                raise ValueError(f'{doc_id}: empty source document')
            selection = doc.get('pages', list(range(1, len(pages) + 1)))
            if (not isinstance(selection, list) or not selection or
                    any(type(v) is not int or v < 1 or v > len(pages) for v in selection) or
                    len(set(selection)) != len(selection)):
                raise ValueError(f'{doc_id}: pages must be unique valid 1-based page numbers')
            should_print = doc.get('print', True)
            if type(should_print) is not bool:
                raise ValueError(f'{doc_id}: print must be true or false')
            pair_id = doc.get('pair_id')
            if pair_id is not None and (not isinstance(pair_id, str) or not pair_id.strip()):
                raise ValueError('pair_id must be a nonempty string')
            canonical = doc.get('canonical_of')
            if canonical is not None and canonical not in ids:
                raise ValueError(f'{doc_id}: canonical_of must reference an earlier canonical document')
            if canonical is not None and ids[canonical].get('canonical_of'):
                raise ValueError(f'{doc_id}: canonical alias chains are not supported')
            if canonical is not None and ids[canonical]['sha256'] != sha:
                if doc.get('canonical_reviewed') is not True or not isinstance(doc.get('canonical_reason'), str) or not doc['canonical_reason'].strip():
                    raise ValueError(f'{doc_id}: different-byte aliases require canonical_reviewed:true and canonical_reason after identity review')
            views = doc.get('views', {})
            if not isinstance(views, dict) or not set(views) <= {str(n) for n in selection}:
                raise ValueError(f'{doc_id}: views must refer to selected source pages')
            record = {'id': doc_id, 'section': section_id, 'kind': section['kind'],
                      'path': str(source), 'sha256': sha, 'source_page_count': len(pages),
                      'selected_pages': selection, 'canonical_of': canonical,
                      'canonical_reviewed': doc.get('canonical_reviewed', False),
                      'canonical_reason': doc.get('canonical_reason'), 'pages': []}
            ids[doc_id] = record
            records.append(record)
            for number, page in enumerate(pages, 1):
                status = 'selected'
                if number not in selection:
                    status = 'not_selected'
                elif canonical is not None:
                    status = 'canonical_alias'
                elif not should_print:
                    status = 'print_false'
                elif (sha, number) in printed:
                    status = 'already_printed'
                elif (sha, number) in seen_pages:
                    status = 'duplicate_bytes'
                page_record = {'page': number, 'status': status}
                if status == 'duplicate_bytes':
                    page_record['duplicate_of'] = seen_pages[(sha, number)]
                record['pages'].append(page_record)
                if pair_id and number in selection:
                    declared_pairs.setdefault(pair_id, []).append({
                        'id': doc_id, 'page': number, 'role': doc.get('role', 'other'),
                        'disposition': status, 'record': page_record})
                if status != 'selected':
                    continue
                view = view_for(doc, number, page)
                seen_pages[(sha, number)] = {'id': doc_id, 'page': number}
                prepared.append({'id': doc_id, 'path': str(source), 'sha256': sha,
                                 'page': number, 'source_page': page,
                                 'role': doc.get('role', 'other'), 'pair_id': doc.get('pair_id'),
                                 'view': view, 'record': page_record})
        pairs = {}
        for item in prepared:
            if item['pair_id']:
                if not isinstance(item['pair_id'], str):
                    raise ValueError('pair_id must be a string')
                pairs.setdefault(item['pair_id'], []).append(item)
        if declared_pairs and layout != 'grid_2x2':
            raise ValueError('Invoice/itinerary pairs require grid_2x2')
        for pair_id, pair in declared_pairs.items():
            if len(pair) != 2 or {v['role'] for v in pair} != {'invoice', 'itinerary'}:
                raise ValueError(f'{pair_id}: a pair requires exactly one invoice page and one itinerary page; use explicit reviewed page selections or separate sections')
            remaining = pairs.get(pair_id, [])
            if len(remaining) == 1:
                omitted = next(v for v in pair if v['disposition'] != 'selected')
                if omitted['disposition'] not in {'print_false', 'already_printed', 'duplicate_bytes', 'canonical_alias'}:
                    raise ValueError(f'{pair_id}: incomplete pair has no audited exclusion')
                remaining[0]['record']['pair_counterpart_exclusion'] = {
                    key: omitted[key] for key in ('id', 'page', 'disposition')}
        units, consumed = [], set()
        for item in prepared:
            pair_id = item['pair_id']
            if not pair_id:
                units.append([item])
            elif pair_id not in consumed:
                units.append(sorted(pairs[pair_id], key=lambda v: v['role'] != 'invoice'))
                consumed.add(pair_id)
        sections.append({'id': section_id, 'kind': section['kind'], 'layout': layout,
                         'orientation': orientation, 'geometry': geo, 'units': units})
    return path, sections, records


def add_guides(page, geo):
    data = io.BytesIO()
    drawing = canvas.Canvas(data, pagesize=[v * MM for v in geo['page_mm']])
    drawing.setStrokeColorRGB(.65, .65, .65)
    drawing.setLineWidth(.35)
    drawing.setDash(3, 3)
    for line in geo['guides_mm']:
        drawing.line(*(v * MM for v in line))
    drawing.save()
    page.merge_page(PdfReader(io.BytesIO(data.getvalue())).pages[0])


def place(destination, item, slot, margin):
    page = item['source_page']
    view = item['view']
    x0, y0, x1, y1 = view['crop_box_points']
    width, height = x1 - x0, y1 - y0
    if width <= 0 or height <= 0:
        raise ValueError('Invalid source geometry')
    x, y, sw, sh = [v * MM for v in slot]
    padding = margin * MM
    inner_w, inner_h = sw - 2 * padding, sh - 2 * padding
    candidates = {0: min(inner_w / width, inner_h / height),
                  90: min(inner_w / height, inner_h / width)}
    rotation = view['rotation']
    if rotation == 'auto':
        rotation = max(candidates, key=candidates.get)
    scale = candidates[rotation]
    fitted_w, fitted_h = (width * scale, height * scale) if rotation == 0 else (height * scale, width * scale)
    dx, dy = x + (sw - fitted_w) / 2, y + (sh - fitted_h) / 2
    transform = Transformation().translate(-x0, -y0)
    if rotation == 90:
        transform = transform.rotate(90).translate(height, 0)
    transform = transform.scale(scale).translate(dx, dy)
    page.cropbox = RectangleObject([x0, y0, x1, y1])
    destination.merge_transformed_page(page, transform, expand=False)
    return {'id': item['id'], 'source_page': item['page'], 'source_sha256': item['sha256'],
            'role': item['role'], 'pair_id': item['pair_id'],
            'slot_mm': list(slot), 'fitted_box_mm': [v / MM for v in [dx, dy, dx + fitted_w, dy + fitted_h]],
            'scale': scale, 'rotation_degrees_counterclockwise': rotation,
            'crop_normalized': view['crop_normalized'], 'crop_reviewed': view['crop_reviewed'],
            'original_crop_box_points': view['original_crop_box_points'],
            'used_crop_box_points': view['crop_box_points'], 'aspect_ratio_preserved': True}


def build(manifest_path, output, printed_ledger=None):
    manifest_path, sections, records = inspect_manifest(manifest_path, printed_ledger)
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Choose a new output directory; prior print runs are immutable')
    output.mkdir(parents=True)
    report = {'schema_version': 1, 'manifest_path': str(manifest_path), 'manifest_sha256': digest(manifest_path),
              'status': 'prepared', 'physical_print_verified': False, 'print_instruction': 'A4; actual size 100%; one PDF page per sheet',
              'documents': records, 'outputs': []}
    ledger = {'schema_version': 1, 'physical_print_verified': False, 'pages': []}
    for section in sections:
        writer = PdfWriter()
        geo, placements, sheets = section['geometry'], [], []
        capacity, used, destination = len(geo['slots_mm']), 0, None
        for unit in section['units']:
            if len(unit) == 2 and destination is not None and used % 2:
                used += 1  # A pair always occupies an entire row, never crosses a cut.
            if destination is None or used + len(unit) > capacity:
                destination = writer.add_blank_page(*(v * MM for v in geo['page_mm']))
                add_guides(destination, geo)
                used = 0
                sheets.append({'page': len(writer.pages), 'guide_lines_mm': geo['guides_mm'], 'used_slots': []})
            for item in unit:
                placement = place(destination, item, geo['slots_mm'][used], geo['margin_mm'])
                placement.update({'output_page': len(writer.pages), 'slot': used + 1})
                placements.append(placement)
                sheets[-1]['used_slots'].append(used + 1)
                item['record'].update({'status': 'prepared', 'output_page': len(writer.pages), 'slot': used + 1})
                ledger['pages'].append({'sha256': item['sha256'], 'page': item['page'], 'id': item['id'],
                                        'section': section['id'], 'status': 'prepared', 'confirmed_by': None, 'confirmation': None})
                used += 1
        if not placements:
            continue
        filename = f"{section['kind']}-{section['id']}.pdf"
        target = output / filename
        writer.write(str(target))
        report['outputs'].append({'file': filename, 'sha256': digest(target), 'section': section['id'],
                                  'kind': section['kind'], 'layout': section['layout'], 'page_size_mm': geo['page_mm'],
                                  'pages': len(writer.pages), 'pieces': len(placements), 'margin_mm': geo['margin_mm'],
                                  'sheets': sheets, 'placements': placements})
    for record in records:
        if digest(record['path']) != record['sha256']:
            raise RuntimeError('A source changed during packing; discard this output and retry from stable sources')
    if not report['outputs']:
        report['status'] = 'no_reprint_needed'
    report['source_files_unchanged'] = True
    report['accounted_source_pages'] = sum(len(record['pages']) for record in records)
    report['prepared_unique_pages'] = len(ledger['pages'])
    (output / 'print-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'print-ledger.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--printed-ledger')
    args = parser.parse_args()
    try:
        report = build(args.manifest, args.output, args.printed_ledger)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'invalid_input', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({'status': report['status'], 'files': len(report['outputs']),
                      'pages': sum(v['pages'] for v in report['outputs']),
                      'report': str(Path(args.output).resolve() / 'print-report.json')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
