---
name: reimbursement-print
description: Prepare local reimbursement drafts from receipt folders, link evidence to expenses, fill generic Chinese Excel forms, and pack supporting documents onto A4 sheets for cutting.
---

# Reimbursement Print

Turn a local receipt folder into editable claim drafts and printable supporting documents. Read [setup and commands](references/setup.md) for the bundled resources and [the job contract](references/job-contract.md) when constructing inputs. This skill works inside Codex; it is not a standalone reimbursement system.

## Intake and grouping

Accept PDFs plus ordinary payment screenshots and any supplied bills, itineraries or approvals. The user should not need to rename files, construct JSON or download XML/OFD companions. Read PDF text first and inspect images locally when needed. Do not upload receipts to an external OCR service without authorization.

Ask for the source folder once if it is not supplied. Preserve original names/content and previous user edits. Agree the grouping with the user. Keep traveler/rider, actual payer, expense owner, handler and recipient separate. When finance reimburses actual payers, use one travel claim per trip and payer and consolidate ordinary expenses per confirmed payer. Never combine different payers merely because they share a trip. Keep reception applications event-specific. Other ordinary expenses use the general expense form. Do not infer business purpose, eligibility, recipients or company policy from merchant names or travel dates.

Create an internal job using the bundled schema. Link invoices, payments, bills, itineraries and approvals to expense IDs. Supporting payment amounts are evidence, never additional expenses. When PDF/XML/OFD versions represent the same invoice, retain originals and print/count one canonical PDF. Compare invoice identity, issuer, date and amount; a hash alone only establishes byte identity. The helpers do not parse or authenticate XML/OFD.

Use blank profile inputs until the user provides their department, handler, expense owner, recipient and bank details. Keep account numbers as strings. Store private profiles and receipt jobs outside the skill/repository. There are no built-in personal names, employers, account routes or approval-platform defaults.

## Draft forms

The generic master provides **差旅费报销单**, **费用报销单** and **业务招待申请单**. Fill a separate workbook using the supplied filler; retain the blank master. Relevant print sheets are listed in the output report. Leave all approval/signature and cash-receipt signature areas blank. An actual bill must not be substituted for a missing prior reception budget.

Read the field map for exact cell locations and capacities. The template has six travel lines and nine general expense lines. Split overflow into linked continuation forms and reconcile their combined total. Never discard details or include unseen rows in a total. Use exact RMB values to two decimal places and reconcile numeric totals with uppercase Mandarin totals. Label outbound, return and intermediate travel segments inside the form when known. Keep a retained cancellation fee separate from a refunded ticket cost. For receptions, retain the confirmed guest name/title in the entered row text. These are source-backed inputs, not inferred policy.

In this generic template, taxi actuals map to the 交通费 amount column and actual meal costs to the 餐费 amount column. This is a field mapping, not an eligibility or payment rule. Leave day/count fields unknown until supported; transport quantity and the paper attachment-count box stay blank in the supplied helper. Adapt the template only after the user's organization confirms its convention. All claimed amounts are explicit expense inputs.

## Automate print preparation

Use [print layouts](references/print-layouts.md) and the separate [print manifest](references/print-manifest.md). The agent constructs inputs and runs the helpers; the user should only supply the folder and unresolved business facts. Use one section per category or claim so forms, receipts, screenshots and itineraries can be printed independently.

For new runs use `print_sheets.py`. Four-up defaults to landscape A4 with **exactly two shared cut lines**, one horizontal and one vertical. There are no per-piece border rectangles. `two_up_136` places two 210 × 136 mm pieces on portrait A4, with two horizontal cut guides and a default 6 mm inset. Confirm the organization's actual cut size before changing it. Keep form titles centered and entered values left-aligned adjacent to their labels without redesigning an approved master.

Use `prepare_print_views.py` to propose exterior-whitespace crops and source/proposal previews. Review every proposed crop before accepting it. Preserve all relevant invoice details, itinerary rows, notes and page context. Automatic orientation compares proportional upright/rotated fits. If text is still too small, use fewer pieces per sheet. Never substitute PDF text extraction for rendered visual review.

Pair invoices with their matched itineraries using `pair_id`. Canonical documents print once, even when referenced by multiple claims. Keep shared evidence allocation in the private case record. Exact byte duplicates are suppressed; different-byte alternatives need an explicit reviewed identity link. Do not infer duplicates from matching amounts alone.

Preserve original files, hashes and prior outputs. `print:false` excludes a confirmed unnecessary reprint while retaining its audit entry. A generated ledger says prepared, never printed. Only user-confirmed printed records suppress pages on the next run. Do not automatically omit hotel stay confirmations or airline payment proof for another organization; these are local policy choices.

Print generated sheets at **100%, one PDF page per sheet**, using their saved orientation. No additional printer N-up setting is needed. Legacy `pack_by_layout.py` jobs remain supported, but the new manifest path provides crop review, orientation, pairing and print-state handling.

## Review and deliver

Reconcile the entire current inbox, explicit attachments and existing case inventory before claiming a document is missing. Match invoice identity and transaction details as well as file hashes. Check expense/evidence matching, refunds versus retained fees, duplicate invoice representations, totals, missing inputs, blank signatures, no detail loss, print sizes and every source-page disposition. Use a fresh output directory for each revision. Report files ready and unresolved inputs concisely. A draft, successful check or print pack never implies approval, submission, payment or organizational acceptance.

The bundled helpers produce filled XLSX files and attachment PDFs. Export only the report's relevant worksheets with an available spreadsheet/PDF tool if a combined cover-plus-evidence PDF is requested; verify the exported geometry and page order. Do not claim this consolidation is performed by the attachment packer itself. Do not submit claims, contact approvers, move money or start a physical print job from preparation alone.

Follow the owning project's archive rules when supplied. Keep real receipts, profiles, bank details, generated claims and business archives outside this public skill. For changes, read [contribution guidance](CONTRIBUTING.md).
