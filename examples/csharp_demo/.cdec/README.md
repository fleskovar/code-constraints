# `.cdec/` — demo configuration for `examples/csharp_demo`

This folder is a worked example of `cdec check` against a small C#
e-commerce model. To try it:

```bash
# from the project root
.venv/Scripts/python.exe -m code_constraints.cli check --config examples/csharp_demo/.cdec --source examples/csharp_demo

# or from within this directory
cd examples/csharp_demo
cdec check
```

## What the rules enforce

- **Layering.** `Catalog` and `Notifications` are leaf packages; `Users`
  may depend only on `Notifications`. `Orders` sits on top and may
  depend on both.
- **Naming.** Every concrete implementation of `INotifier` must end in
  `Notifier`.
- **Dangling.** Classes with no incoming references are flagged, except
  for the `Admin`, `Order`, and concrete-notifier entry points that
  application bootstrap code is expected to wire up.
- **Stability.** `INotifier`'s operations are locked — adding or
  removing methods requires a deliberate `--update-baseline` /
  `--update-reference` pass.

## Failure messages

Every rule in [rules.yaml](rules.yaml) carries a `message:` block that
explains *why* the rule exists and *how* to address the violation.
Placeholders like `{qualified_name}`, `{source}`, `{target}`, `{cycle}`,
`{fanout}`, and `{limit}` are interpolated at violation time; use
`message: |` to write multi-line guidance (continuation lines are
indented by the human-readable report).

## Trying it out

Edit any file in this folder and re-run `cdec check`. For example:

- Add a new class outside the namespace → `no-new-classes` warns.
- Rename `SmsNotifier` to `SmsSender` → `subclass-naming` errors.
- Add a `using Orders;` reference to a `Catalog` class → the
  `catalog-is-a-leaf-package` rule fails.
- Add a method to `INotifier` → `lock-inotifier` errors until you
  intentionally re-snapshot the reference with
  `cdec check --update-reference`.
