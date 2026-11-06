# Print layouts

Use `print_sheets.py` for new runs. Codex builds the [print manifest](print-manifest.md), checks the sources and reviews the resulting sheets. Financial jobs and print manifests are separate so changing a cut layout cannot change claim amounts or payers.

| Preset | A4 orientation | Finished piece | Cuts |
| --- | --- | --- | --- |
| `grid_2x2` | Landscape by default | 148.5 × 105 mm | One central horizontal and one central vertical cut |
| `grid_2x2` | Portrait when requested | 105 × 148.5 mm | The same two central cuts |
| `two_up_136` | Portrait | 210 × 136 mm | Horizontal guides 136 and 272 mm below the top edge |
| `strips_1x4` | Portrait by default | 210 × 74.25 mm | Three horizontal cuts |

The paper edges are the outside piece edges. There are no individual image-border rectangles or dimension captions. Each piece has a 6 mm content inset by default, adjustable from 2 to 15 mm. Incomplete sheets retain blank slots rather than repeating a document. Print **A4, actual size 100%, one PDF page per sheet**. Do not apply another printer N-up setting.

## Choose a layout by content

Use four-up for screenshots and evidence that remains readable. Landscape four-up supports two invoice–itinerary pairs, each pair in one row. Use two-up for exported landscape covers or larger invoices when it matches the user's approved cut size. A 220 mm cover cannot retain exact width on portrait A4. Confirm the reduced 210 mm width or choose another layout. Preserve the editable form master and apply imposition only to a separate exported PDF.

The two-up preset is a reusable option, not a universal employer requirement. Choose or confirm the organization's physical dimensions. Keep forms, receipts, payment screenshots and itinerary groups in separate manifest sections so users can print only what is still needed.

## Crop and rotate without losing evidence

`prepare_print_views.py` proposes exterior-whitespace crops and generates source/proposal previews. It keeps internal whitespace and all detected marks, skips forms and records hashes. Proposals are unreviewed. Codex visually checks the full source and preview before setting `reviewed:true` for an accepted crop. The packer refuses unreviewed non-full crops.

Do not reuse fixed crop coordinates from another receipt. Invoice number, purchaser/seller information, dates, amounts, passenger/rider names, all route rows, notes and required page context must remain visible. Ads or redundant app interface can be excluded only through a separately reviewed derived view. Original files are never edited. Extracted text can survive outside a PDF clip, so matching text alone does not validate a crop.

The packer compares upright and 90-degree proportional fits with `rotation:"auto"`. Set `0` or `90` when a reviewed orientation is better. It never stretches the source. If route text is still too small, use fewer pieces per sheet. Inspect rendered output at its intended print size.

## Compatibility

`pack_by_layout.py --job ...` remains available for older financial jobs. Its payment grid now uses two shared cut lines. Ordinary evidence and `ctrip_1x4` retain historical geometry. New automation should use `print_sheets.py`, which supports reviewed crops, orientation, categories, pairing, deduplication and user-confirmed printed-state handling.
