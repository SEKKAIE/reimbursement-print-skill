# Contributing

Use a branch or fork and submit a pull request. A repository collaborator with write access can push their branch directly; everyone else can use a fork. Repository access invitations are a separate owner action.

Keep receipts, bank details, organization names, employee names, private defaults, real invoice numbers and generated claims outside this repository. Use only synthetic data in examples/tests. Do not add a local export bundle, source-provenance manifest or a business knowledge base. The public templates must remain generic; organization-specific rules belong in private local configuration.

Before proposing changes:

```text
python -m pip install -r requirements.txt
python tools/validate_public.py
python -m unittest discover -s tests -v
```

If changing the form filler, also run it with the empty example or a synthetic job using Codex's `@oai/artifact-tool` runtime. Confirm totals, blank signatures, row-overflow handling and print geometry. The Node runtime is not redistributed, so the standard Python checks cannot establish that a filler change works. Record that validation in the pull request.

Preserve whole Ctrip source pages, proportional layout, `print:false`, separation of expenses from evidence, and previous user output files. Describe observable behavior and relevant checks. Avoid adding policy defaults or claiming support for environments that were not tested.
