"""Propose exterior-whitespace crops for local print evidence, pending visual review.

The resulting manifest is not an approval. Inspect every preview, retain required
marks, and set reviewed:true only for accepted views before print_sheets.py.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import io
import json
import math
import os
import sys

from PIL import Image, ImageChops, ImageDraw
import pypdfium2 as pdfium
from pypdf import PdfWriter

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from print_sheets import FORMATS, geometry, source_pages, view_for


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exterior_crop(image):
    """Detect all nonwhite pixels, including near-white marks; add safety padding."""
    rgb = image.convert('RGB')
    box = ImageChops.difference(rgb, Image.new('RGB', rgb.size, 'white')).getbbox()
    if box is None:
        return [0, 0, 1, 1], None
    padding = max(2, math.ceil(min(rgb.size) * .01))
    left, top, right, bottom = box
    padded = (max(0, left - padding), max(0, top - padding),
              min(rgb.width, right + padding), min(rgb.height, bottom + padding))
    return [padded[0] / rgb.width, padded[1] / rgb.height,
            padded[2] / rgb.width, padded[3] / rgb.height], list(box)


def render_page(page, dpi):
    writer = PdfWriter()
    writer.add_page(page)
    stream = io.BytesIO()
    writer.write(stream)
    with pdfium.PdfDocument(stream.getvalue()) as pdf:
        return pdf[0].render(scale=dpi / 72).to_pil().convert('RGB')


def preview(image, crop, label, target):
    """Full source alongside proposal; full-size source remains untouched."""
    width, height = image.size
    bounds = (math.floor(crop[0] * width), math.floor(crop[1] * height),
              math.ceil(crop[2] * width), math.ceil(crop[3] * height))
    original = image.copy()
    ImageDraw.Draw(original).rectangle(bounds, outline=(210, 40, 40), width=max(2, width // 250))
    cropped = image.crop(bounds)
    board = Image.new('RGB', (1240, 900), (235, 235, 235))
    draw = ImageDraw.Draw(board)
    draw.text((16, 12), label, fill='black')
    draw.text((16, 36), 'Full source; red box is proposed crop', fill='black')
    draw.text((636, 36), 'Proposed view; verify every mark before accepting', fill='black')
    for index, part in enumerate((original, cropped)):
        part.thumbnail((600, 820), Image.Resampling.LANCZOS)
        board.paste(part, (index * 620 + 10 + (600 - part.width) // 2, 65))
    board.save(target)


def prepare(manifest_path, output, dpi=180):
    manifest_path, output = Path(manifest_path).resolve(), Path(output).resolve()
    if type(dpi) is not int or not 72 <= dpi <= 300:
        raise ValueError('dpi must be an integer between 72 and 300')
    if output.exists():
        raise FileExistsError('Choose a new proposal directory')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if manifest.get('schema_version') != 1 or not isinstance(manifest.get('sections'), list):
        raise ValueError('Manifest requires schema_version 1 and sections array')
    result = copy.deepcopy(manifest)
    planned, ids, section_ids = [], set(), set()
    # Validate every source before creating any output.
    for section in result['sections']:
        section_id = section.get('id')
        if not isinstance(section_id, str) or not section_id or section_id in section_ids:
            raise ValueError('Sections require unique nonempty IDs')
        section_ids.add(section_id)
        if section.get('kind') not in {'forms', 'evidence'}:
            raise ValueError('Section kind must be forms or evidence')
        layout = section.get('layout', 'grid_2x2')
        orientation = section.get('orientation', 'landscape' if layout == 'grid_2x2' else 'portrait')
        geometry(layout, orientation, section.get('margin_mm', 6))
        if not isinstance(section.get('documents'), list):
            raise ValueError('Section documents must be an array')
        for document in section['documents']:
            doc_id = document.get('id')
            if not isinstance(doc_id, str) or not doc_id or doc_id in ids:
                raise ValueError('Document IDs must be globally unique and nonempty')
            ids.add(doc_id)
            if not isinstance(document.get('path'), str) or not document['path']:
                raise ValueError('Document path required')
            path = Path(document['path'])
            path = (manifest_path.parent / path).resolve() if not path.is_absolute() else path.resolve()
            if not path.is_file() or path.suffix.lower() not in FORMATS:
                raise ValueError(f'{doc_id}: missing or unsupported source')
            pages = source_pages(path)
            selection = document.get('pages', list(range(1, len(pages) + 1)))
            if (not isinstance(selection, list) or not selection or
                    any(type(n) is not int or not 1 <= n <= len(pages) for n in selection) or
                    len(set(selection)) != len(selection)):
                raise ValueError(f'{doc_id}: invalid page selection')
            views = document.get('views', {})
            if not isinstance(views, dict) or not set(views) <= {str(n) for n in selection}:
                raise ValueError(f'{doc_id}: views must refer to selected pages')
            if type(document.get('print', True)) is not bool:
                raise ValueError(f'{doc_id}: print must be boolean')
            # Relocation preserves what each relative source path resolves to.
            try:
                document['path'] = Path(os.path.relpath(path, output)).as_posix()
            except ValueError:
                document['path'] = str(path)
            for number in selection:
                old_view = views.get(str(number), {})
                if not isinstance(old_view, dict):
                    raise ValueError(f'{doc_id}: page view must be an object')
                if old_view.get('reviewed') is True:
                    view_for(document, number, pages[number - 1])
                planned.append((section, document, path, number, pages[number - 1], digest(path)))
    output.mkdir(parents=True)
    preview_dir = output / 'previews'
    preview_dir.mkdir()
    records, thumbs = [], []
    for section, document, path, number, page, checksum in planned:
        old_view = document.get('views', {}).get(str(number), {})
        record = {'document_id': document['id'], 'section_id': section['id'], 'page': number,
                  'source_path': str(path), 'source_sha256': checksum}
        if old_view.get('reviewed') is True:
            record['status'] = 'existing_reviewed_view_retained'
        elif section['kind'] == 'forms':
            record['status'] = 'form_geometry_unchanged'
        elif document.get('print', True) is False or document.get('canonical_of'):
            record['status'] = 'excluded_or_canonical_alias_unchanged'
        else:
            image = render_page(page, dpi)
            crop, ink = exterior_crop(image)
            view = {**old_view, 'crop': crop, 'reviewed': False}
            view.setdefault('rotation', 'auto')
            document.setdefault('views', {})[str(number)] = view
            target = preview_dir / f'view-{len(thumbs) + 1:04d}.png'
            preview(image, crop, f"View {len(thumbs) + 1:04d} / page {number}", target)
            thumbs.append(target)
            record.update({'status': 'proposal_requires_visual_review', 'crop': crop,
                           'detected_ink_bbox_pixels': ink, 'render_size_pixels': list(image.size),
                           'preview': target.relative_to(output).as_posix(), 'reviewed': False})
        if digest(path) != checksum:
            raise ValueError(f"{document['id']}: source changed during proposal generation")
        records.append(record)
    # Numbered thumbnail contact sheet links to readable individual comparisons.
    if thumbs:
        sheet = Image.new('RGB', (1240, math.ceil(len(thumbs) / 2) * 450), 'white')
        for i, path in enumerate(thumbs):
            with Image.open(path) as im:
                im.thumbnail((620, 450), Image.Resampling.LANCZOS)
                sheet.paste(im, ((i % 2) * 620, (i // 2) * 450))
        sheet.save(output / 'contact-sheet.png')
    (output / 'print-manifest.proposed.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report = {'schema_version': 1, 'source_manifest_sha256': digest(manifest_path),
              'status': 'visual_review_required', 'dpi': dpi, 'records': records,
              'limits': 'Exterior whitespace proposal only. No internal whitespace, headers, advertisements or footer content is removed. Review the full source and proposed view before accepting; originals are unchanged.'}
    (output / 'view-proposals.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--dpi', type=int, default=180)
    args = parser.parse_args()
    report = prepare(args.manifest, args.output, args.dpi)
    print(json.dumps({'status': report['status'], 'pages': len(report['records']), 'output': str(Path(args.output).resolve())}))


if __name__ == '__main__':
    main()
