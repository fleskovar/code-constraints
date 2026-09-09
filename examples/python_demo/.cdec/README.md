# `.cdec/` — demo configuration for `examples/python_demo`

This folder is a worked example of `cdec check` against a small Python
e-commerce model — the Python port of `examples/csharp_demo`. To try
it:

```bash
# from the project root
.venv/Scripts/python.exe -m code_constraints.cli check --config examples/python_demo/.cdec --source examples/python_demo

# or from within this directory
cd examples/python_demo
cdec check
```

## What the rules enforce

- **Layering.** `catalog` and `notifications` are leaf packages;
  `users` may depend only on `notifications`. `orders` sits on top and
  may depend on both.
- **Naming.** Every concrete subclass of `notifications.Notification`
  must end in `Notifier` (so `EmailNotifier`, `SmsNotifier`, …).
- **Dangling.** Classes with no incoming references are flagged,
  except for the `Admin`, `Order`, and concrete-notifier entry points
  that application bootstrap code is expected to wire up.
- **Stability.** `Notification`'s operations are locked — adding or
  removing methods requires a deliberate `--update-baseline` /
  `--update-reference` pass.

## Failure messages

Every rule in [rules.yaml](rules.yaml) carries a `message:` block that
explains *why* the rule exists and *how* to address the violation.
Placeholders like `{qualified_name}`, `{source}`, `{target}`,
`{cycle}`, `{fanout}`, and `{limit}` are interpolated at violation
time; use `message: |` to write multi-line guidance (continuation
lines are indented by the human-readable report).

## Trying it out

Edit any file in this folder and re-run `cdec check`. For example:

- Add a new class outside the existing packages → `no-new-classes`
  warns.
- Rename `SmsNotifier` to `SmsSender` →
  `notifier-implementations-must-end-in-Notifier` errors.
- Add a `from orders.cart import Cart` to a `catalog` module and hold
  one as a field → the `catalog-is-a-leaf-package` rule fails.
- Add a method to `Notification` → `lock-notification-abc` errors
  until you intentionally re-snapshot the reference with
  `cdec check --update-reference`.
