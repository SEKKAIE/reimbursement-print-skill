# Setup and commands

All package paths are relative to the installed skill folder, represented below by `<skill>`. Keep real jobs and outputs outside that folder. The blank master, field map, filler and print-geometry helper are in `assets/package/forms/`; evidence helpers are in `assets/package/scripts/`; schema and empty example are in `assets/package/schema/`.

Use Codex's workspace-dependency discovery when available to locate the bundled Python/Node runtimes. The filler requires Node.js and `@oai/artifact-tool`. It resolves that package from its environment or a configured dependency root; set `CODEX_BUNDLED_NODE_ROOT` when necessary. Set `CODEX_BUNDLED_PYTHON` to the Python executable used by the print-geometry helper if automatic discovery is unsuitable. Do not copy a private machine's absolute paths into the skill.

Install Python dependencies in the selected environment if absent:

```text
python -m pip install -r <skill>/requirements.txt
```

Review the job without creating an attachment PDF:

```text
python <skill>/assets/package/scripts/prepare_receipts.py --job <absolute-job.json> --output <new-check-directory> --check-only
```

Generate supporting-document PDFs, including Ctrip four-row layouts:

```text
python <skill>/assets/package/scripts/pack_by_layout.py --job <absolute-job.json> --output <new-print-directory>
```

Create a separate filled workbook:

```text
node <skill>/assets/package/forms/fill_forms.mjs --job <absolute-job.json> --output <new-form-directory>
```

The filler writes `reimbursement-<claim_type>-draft.xlsx` and `filled-form-report.json`. The report's `print_sheets` selects travel/ordinary expense's relevant claim form or reception's expense form plus application. Do not print the instruction sheet or unused claim sheets. Keep saved scales: cover 100%, application 90%.

Packing writes `processing-report.json` and an attachment PDF when printable evidence exists. `print:false` keeps evidence in hashes/linkage/supporting totals but excludes it from packing. All-excluded evidence reports `no_reprint_needed` without an empty PDF. Source companions are metadata; their content is not automatically read or hashed by these helpers. Warnings and incomplete amounts require review.

The XLSX-to-cover-PDF export and final combined-PDF assembly are agent steps using the destination environment's available tools. Preserve approximately 220 × 136 mm covers and 198 × 86.5 mm applications, inspect the exported pages, then append each claim's evidence in matching order. Do not treat worksheet-render pixels alone as proof of physical print dimensions.
