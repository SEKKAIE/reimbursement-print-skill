# Job contract

Use the bundled [schema](../assets/package/schema/job.schema.json) and [empty example](../assets/package/schema/job.example.json). Codex constructs this internal record from source documents; the end user need not author JSON.

- Root: `schema_version:1`, `claim_type` (`travel`, `reception`, `expense`), `profile`, `expenses`, `evidence`.
- Profile fields are blank by default. Separate `expense_owner`, `handler` and `recipient`. An optional `organization` supplies the generic heading. Keep `account` a string. Never commit populated private profiles.
- Each expense has unique `id`, supported `category`, RMB `amount` and `evidence_ids`. Optional date, purpose, route and counts come from evidence or user confirmation. A payment is linked proof, not a second expense.
- Evidence has unique `id`, `path`, `role` (`invoice`, `payment`, `bill`, `itinerary`, `approval`, `other`). Relative paths resolve against the job JSON's folder. Optional `amount` describes supporting evidence. `print:false` excludes confirmed unnecessary reprints. `print_layout:"ctrip_1x4"` selects whole-page Ctrip strips.
- `claim.date` and `claim.period` are source/user supplied; do not infer an expense month from a download timestamp. `claim.attachment_count` remains null in this template.
- `reception_application` contains the actual guest, headcount, event time/location, host attendees, purpose and prior estimated budget. Keep the estimate distinct from actual paid costs. Missing values stay blank.
- `source_companions` links alternative invoice formats to canonical evidence IDs without adding print pages or expense amounts.

Use exact nonnegative amounts with at most two decimal places. Confirm refunds/credits or any unsupported case rather than silently taking absolute values. Every claimed amount is an explicit expense input. The helpers do not determine eligibility under an employer's policy.

There are six travel rows and nine general-expense rows per form. Split overflow to linked continuations. Leave signatures, attachment-count and unknown traffic-day fields blank. The [field map](../assets/package/forms/field-map.json) defines cells, totals, uppercase amounts, signature regions and print geometry.

For print-only revisions, use the separate [print manifest](print-manifest.md). It adds no expense amounts and does not change financial grouping. Keep payer/rider/recipient reconciliation and source-document identity in the local case record. The existing filler is not a payer inference or automatic claim-splitting engine.
