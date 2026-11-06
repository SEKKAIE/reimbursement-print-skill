# Job contract

Use the bundled [schema](../assets/package/schema/job.schema.json) and [empty example](../assets/package/schema/job.example.json). Codex constructs this internal record from source documents; the end user need not author JSON.

- Root: `schema_version:1`, `claim_type` (`travel`, `reception`, `expense`), `profile`, `expenses`, `evidence`.
- Profile fields are blank by default. Separate `expense_owner`, `handler` and `recipient`. An optional `organization` supplies the generic heading. Keep `account` a string. Never commit populated private profiles.
- Each expense has unique `id`, supported `category`, RMB `amount` and `evidence_ids`. Optional date, purpose, route and counts come from evidence or user confirmation. A payment is linked proof, not a second expense.
- Evidence has unique `id`, `path`, `role` (`invoice`, `payment`, `bill`, `itinerary`, `approval`, `other`). Relative paths resolve against the job JSON's folder. Optional `amount` describes supporting evidence. `print:false` excludes confirmed unnecessary reprints. `print_layout:"ctrip_1x4"` selects whole-page Ctrip strips.
- Optional `claim.subject_name` is the explicitly confirmed person being reimbursed. It replaces the travel/expense cover remarks with that name only and never changes profile recipient, handler or bank values. `claim.single_traveler:true` requires a travel claim, nonblank subject_name and `ticket_count:1` on every flight row. The name is not inferred from a payer or recipient.
- Optional `expenses[].other_amount` is an additional retained ancillary amount on a flight/rail row, printed under 其他 alongside the base `amount`. A positive amount requires nonempty `other_evidence_ids`, a subset of that row’s `evidence_ids`. Remove its separate other-expense row. Both checker and filler total base plus ancillary once and reject a standalone other expense reusing the same fee proof. Shared invoices can support multiple underlying flight legs; source allocation remains in the private case ledger.
- `claim.date` and `claim.period` are source/user supplied; do not infer an expense month from a download timestamp. `claim.attachment_count` remains null in this template.
- `reception_application` contains the actual guest, headcount, event time/location, host attendees, purpose and prior estimated budget. Keep the estimate distinct from actual paid costs. Missing values stay blank.
- `source_companions` links alternative invoice formats to canonical evidence IDs without adding print pages or expense amounts.

Use exact nonnegative amounts with at most two decimal places. Confirm refunds/credits or any unsupported case rather than silently taking absolute values. Every claimed amount is an explicit expense input. The helpers do not determine eligibility under an employer's policy.

There are six travel rows and nine general-expense rows per form. Split overflow to linked continuations. Leave signatures, attachment-count and unknown traffic-day fields blank. The [field map](../assets/package/forms/field-map.json) defines cells, totals, uppercase amounts, signature regions and print geometry.

For print-only revisions, use the separate [print manifest](print-manifest.md). It adds no expense amounts and does not change financial grouping. Keep payer/rider/recipient reconciliation and source-document identity in the local case record. The existing filler is not a payer inference or automatic claim-splitting engine.

For individual flight covers, establish purpose and mode once when missing, then form the approved concise reason (for example `出差机票`). Use separate date/route rows for each actual leg and link an ancillary fee to its correct leg. Do not relabel an uncertain fee as baggage/service/cancellation without evidence, or mistake a refund credit for a positive fee.
