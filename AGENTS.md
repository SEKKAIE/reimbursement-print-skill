# Repository instructions

This repository is a generic public Codex skill. Never add real organization/person profiles, receipts, banking details, invoice identifiers, private source paths, conversation exports, provenance from private workspaces or populated claim outputs.

Keep the generic templates, job contract, helper behavior and documentation aligned. Examples and tests use synthetic data. Keep mutable user jobs outside this repository. Do not infer a company policy from template column labels.

Run `python tools/validate_public.py` and `python -m unittest discover -s tests -v` for relevant changes. If changing the XLSX filler or templates, validate with the required Codex spreadsheet runtime and retain blank signatures and print geometry. Keep changes proportional; do not add deployment, automatic submission, approval or payment behavior.
