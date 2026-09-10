# `.cdec/` — demo configuration for `tests/fixtures/python_demo`

This folder is a worked example of `cdec check`. To try it:

```bash
# from the project root
.venv/Scripts/python.exe -m code_constraints.cli check --config tests/fixtures/python_demo/.cdec

# or from within this directory
cd tests/fixtures/python_demo
cdec check
```

The committed `reference.xmi` is a snapshot of the current fixture, so a
plain `cdec check` should report no diff-scope violations. Try adding a
new class to `animals/` or `store/` and re-running — the `no-new-classes`
rule will flag it. Run `cdec check --automatic-exceptions reference` to accept the
drift.

`rules.yaml` deliberately includes one example of every supported rule
type — copy it into your own project as a starting point. Each rule
carries a `message:` block explaining *why* it exists; placeholders like
`{qualified_name}`, `{source}`, `{target}`, `{cycle}`, `{fanout}`, and
`{limit}` are filled in at violation time. Use `message: |` to write
multi-line guidance — the report indents continuation lines.
