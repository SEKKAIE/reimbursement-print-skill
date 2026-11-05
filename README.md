# Reimbursement Print

A Codex skill for turning local receipt folders into editable Chinese reimbursement forms and A4 supporting-document print packs.

Give Codex a folder of PDFs and payment screenshots. The skill guides evidence matching, missing-information review, Excel filling and proportional print layouts. It includes generic travel, expense and client-reception forms, plus a four-row layout for whole Ctrip flight/hotel pages that can be cut after printing.

## Install in Codex

Clone the repository into your Codex skills directory:

```powershell
git clone https://github.com/SEKKAIE/reimbursement-print-skill.git "$HOME/.codex/skills/reimbursement-print"
```

For a ZIP installation, extract the repository and rename/move its folder to `~/.codex/skills/reimbursement-print`. That folder must directly contain `SKILL.md`, `agents`, `references` and `assets`. Refresh or restart Codex if the new skill is not discovered.

Then tell Codex:

```text
Use $reimbursement-print to process the receipts in <my receipt folder>.
Keep unknown profile and bank fields blank, show missing evidence,
and prepare editable Excel forms plus A4 supporting-document PDFs.
```

You can also ask in Chinese: `使用 $reimbursement-print 处理这个票据文件夹，填写报销表单并准备打印材料。`

## What is included

| File | Purpose |
| --- | --- |
| [SKILL.md](SKILL.md) | Instructions for the Codex handling the batch |
| [Setup](references/setup.md) | Runtime requirements and exact helper commands |
| [Job contract](references/job-contract.md) | How expenses, evidence and private profile inputs connect |
| [Print layouts](references/print-layouts.md) | Sizes, Ctrip four-row packing and print settings |
| [Generic Excel master](assets/package/forms/reimbursement-forms.xlsx) | Expense, travel and reception-application templates |
| [Form filler](assets/package/forms/fill_forms.mjs) | Creates a separate filled XLSX and a review report |
| [Attachment packer](assets/package/scripts/pack_by_layout.py) | Creates supporting-document PDFs with cut guides |
| [Schema and empty example](assets/package/schema/job.schema.json) | Machine-readable job inputs |

The bundle contains generic templates and code. Configure your actual organization, people, bank details and approval rules locally. It does not include real receipts, transactions, personal profiles, company policies or a business archive.

## Requirements and limits

- Python with Pillow, pypdf and reportlab for checks/packing; tested versions are in [requirements.txt](requirements.txt).
- Node.js and Codex's **`@oai/artifact-tool`** runtime package for the XLSX filler. Ordinary Node alone is insufficient. Runtime binaries are not redistributed here.
- The helpers create filled workbooks and attachment PDFs. Codex must use an available spreadsheet/PDF tool to export the selected cover sheets and assemble a combined PDF when requested.
- Inputs are drafts reviewed by the user. There is no invoice-authenticity service, automatic approval, submission, payment, background monitoring or physical printing.
- Local Windows/Codex execution is the current tested environment. Do not assume other hosts or a particular printer have been validated.

The cover is approximately 220 × 136 mm. Supporting pieces are smaller. Ctrip documents are arranged as **one column × four rows on A4**, each source page kept whole. Print output PDFs at **100%, one PDF page per sheet**; the layout is already imposed.

## Update and contribute

Inside your installed folder, use `git pull --ff-only` to update when it has no local edits. Keep organization-specific profiles and receipts elsewhere so updates do not overwrite them. To maintain code, make a branch or fork, use synthetic test data and open a pull request. See [CONTRIBUTING.md](CONTRIBUTING.md).

Access to push changes is controlled by GitHub repository permissions; sharing this URL does not grant write access. A colleague can propose changes through a fork and pull request, or an owner can separately invite them as a collaborator.

License: see [LICENSE](LICENSE).
