# Print manifest

Codex creates this record outside the repository. Users supply ordinary files and describe the desired output; they do not need to write JSON. The financial [job contract](job-contract.md) remains separate.

The manifest contains `schema_version:1` and `sections`. Each section produces its own PDF. The [empty example](../assets/package/schema/print-manifest.example.json) is a starting point.

```json
{
  "schema_version": 1,
  "sections": [{
    "id": "taxi-evidence",
    "kind": "evidence",
    "layout": "grid_2x2",
    "orientation": "landscape",
    "margin_mm": 6,
    "documents": [
      {"id":"invoice-1","path":"invoice.pdf","role":"invoice","pair_id":"pair-1"},
      {"id":"itinerary-1","path":"itinerary.pdf","role":"itinerary","pair_id":"pair-1"}
    ]
  }]
}
```

- Section `id` is a unique filename-safe string of letters, numbers, hyphens or underscores, starting with a letter/number, at most 64 characters. `kind` is `forms` or `evidence`.
- `layout` is `grid_2x2`, `two_up_136` or `strips_1x4`. Four-up defaults to landscape; the others default to portrait. Two-up requires portrait. `margin_mm` defaults to 6, within 2–15.
- Each document requires globally unique `id` and `path`. Relative paths resolve against the manifest folder. PDF and single-frame PNG/JPEG/WebP/BMP are supported. `role` identifies the evidence type.
- `pages` optionally selects unique one-based source page numbers. Omitted pages are audited as `not_selected`. Keep them in the review inventory and record the reason for exclusion in the local case record.
- `print:false` retains a document in the audit without packing it. Use only for a confirmed exclusion, such as an already-held physical bill or a proof the user expressly excludes.
- Shared `pair_id` declares exactly one selected invoice page and one selected itinerary page, in a four-up section. The complete pair stays in the same row. If one member is excluded or confirmed already printed, only the outstanding member prints, with the exclusion audited. Multipage evidence needs explicit page groups or a separate section so no page is silently lost.
- Exact duplicate source hashes/pages print once across sections. `canonical_of` references an earlier canonical document for a reviewed same-document alternative. Different-byte aliases require `canonical_reviewed:true` and a meaningful `canonical_reason`. Matching amounts alone do not establish a duplicate. Choose a printable canonical representation when printing is needed.
- `views` optionally maps source page strings, such as `"1"`, to `{ "crop":[0,0,1,1], "reviewed":true, "rotation":"auto" }`. Crop bounds are normalized `[left,top,right,bottom]` against the displayed page, from the top-left. Non-full crops require `reviewed:true`. Rotation is `"auto"`, `0` or `90`; 90 means counterclockwise. Do not copy a prior file's crop coordinates blindly.

The tool validates input and refuses an existing output directory. It writes separate `forms-<section>.pdf` or `evidence-<section>.pdf`, plus `print-report.json` and `print-ledger.json`. The report includes original hashes, source pages, exclusions, duplicate decisions, crop/rotation, placement and cut-line geometry. Empty sections produce no blank PDFs.

## Printed-state ledger

Generated pages have `status:"prepared"`; they are not treated as printed. Use `--printed-ledger` only after the user identifies which materials they actually printed. Its structure is `schema_version:1` with a `pages` array. Each confirmed entry contains the source `sha256`, one-based `page`, `status:"printed"`, `confirmed_by:"user"` and nonempty `confirmation` recording the user's statement. The tool suppresses only matching source hash/page entries. Keep this ledger private and never infer physical printing from a generated PDF.

To reprint intentionally, omit the applicable printed entries or omit the ledger for that new run. Keep the old ledger and output immutable. Broad statements such as “screenshots are printed” need an unambiguous source list before updating individual page records.
