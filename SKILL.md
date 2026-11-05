---
name: reimbursement-print
description: Prepare local reimbursement drafts from receipt folders, link evidence to expenses, fill generic Chinese Excel forms, and pack supporting documents onto A4 sheets for cutting.
---

# Reimbursement Print

Turn a local receipt folder into editable claim drafts and printable supporting documents. Read [setup and commands](references/setup.md) for the bundled resources and [the job contract](references/job-contract.md) when constructing inputs. This skill works inside Codex; it is not a standalone reimbursement system.

## Intake and grouping

Accept PDFs plus ordinary payment screenshots and any supplied bills, itineraries or approvals. The user should not need to rename files, construct JSON or download XML/OFD companions. Read PDF text first and inspect images locally when needed. Do not upload receipts to an external OCR service without authorization.

Ask for the source folder once if it is not supplied. Preserve original names/content and previous user edits. Make one claim per trip or client reception unless the user specifies another grouping. Other ordinary expenses use the general expense form. Do not infer business purpose, eligibility, recipients or company policy from merchant names or travel dates.

Create an internal job using the bundled schema. Link invoices, payments, bills, itineraries and approvals to expense IDs. Supporting payment amounts are evidence, never additional expenses. When PDF/XML/OFD versions represent the same invoice, retain originals and print/count one canonical PDF. Compare invoice identity, issuer, date and amount; a hash alone only establishes byte identity. The helpers do not parse or authenticate XML/OFD.

Use blank profile inputs until the user provides their department, handler, expense owner, recipient and bank details. Keep account numbers as strings. Store private profiles and receipt jobs outside the skill/repository. There are no built-in personal names, employers, account routes or approval-platform defaults.

## Draft forms

The generic master provides **差旅费报销单**, **费用报销单** and **业务招待申请单**. Fill a separate workbook using the supplied filler; retain the blank master. Relevant print sheets are listed in the output report. Leave all approval/signature and cash-receipt signature areas blank. An actual bill must not be substituted for a missing prior reception budget.

Read the field map for exact cell locations and capacities. The template has six travel lines and nine general expense lines. Split overflow into linked continuation forms and reconcile their combined total. Never discard details or include unseen rows in a total. Use exact RMB values to two decimal places and reconcile numeric totals with uppercase Mandarin totals.

In this generic template, taxi actuals map to the 交通费 amount column and actual meal costs to the 餐费 amount column. This is a field mapping, not an eligibility or payment rule. Leave day/count fields unknown until supported; transport quantity and the paper attachment-count box stay blank in the supplied helper. Adapt the template only after the user's organization confirms its convention. All claimed amounts are explicit expense inputs.

## Print supporting documents

Use [print layouts](references/print-layouts.md). The cover is approximately **220 × 136 mm**. Ordinary evidence pieces are **198 × 126 mm**, payment images **96 × 126 mm**, and the reception application approximately **198 × 86.5 mm**. Preserve aspect ratio and full source content; never silently crop evidence. Review the resulting physical-size layout before delivery.

For Ctrip flight/hotel PDFs, mark `print_layout:"ctrip_1x4"`: four complete source pages stacked vertically on one portrait A4 sheet, one page per **198 × 66 mm** strip, with cut guides. No splitting or stretching. Unused rows remain empty. This layout deliberately reduces text; confirm an alternative if a particular document becomes unusable. Print the generated PDF at **100%, one PDF page per sheet**, then cut manually. Do not apply an additional four-pages-per-sheet setting.

An already-held physical original can be marked `print:false` only when the user confirms it need not be reprinted. It remains linked and checked but is excluded from packing. If all evidence is excluded, no attachment PDF is required. Preserve the workbook's saved print scales: covers 100%, reception application 90%.

## Review and deliver

Check expense/evidence matching, duplicate invoice representations, totals, missing documents/inputs, blank signatures, no detail loss and print sizes. Use a fresh output directory for each revision. Report files ready and unresolved inputs concisely. A draft, successful check or print pack never implies approval, submission, payment or organizational acceptance.

The bundled helpers produce filled XLSX files and attachment PDFs. Export only the report's relevant worksheets with an available spreadsheet/PDF tool if a combined cover-plus-evidence PDF is requested; verify the exported geometry and page order. Do not claim this consolidation is performed by the attachment packer itself. Do not submit claims, contact approvers, move money or start a physical print job from preparation alone.

Follow the owning project's archive rules when supplied. Keep real receipts, profiles, bank details, generated claims and business archives outside this public skill. For changes, read [contribution guidance](CONTRIBUTING.md).
