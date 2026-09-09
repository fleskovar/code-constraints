# TypeScript example

The same bookstore domain as `python_demo` / `csharp_demo`, ported to plain
TypeScript so you can see the class / package / inheritance / association
edges the TypeScript parser produces.

Layout:

```
src/
  catalog/        Author, Book
  notifications/  Notification (abstract), EmailNotifier, SmsNotifier
  users/          User (abstract), Customer, Admin
  orders/         OrderItem, Cart, Order, OrderStatus (enum)
```

Cross-package dependencies the package diagram should highlight:

- `orders` → `catalog` (`OrderItem.book: Book`)
- `orders` → `users` (`Cart.customer: Customer`)
- `users` → `notifications` (`Customer.notifier: Notification`)

## Running

Web UI:

```bash
.venv/Scripts/python.exe -m code_constraints.cli serve
# → http://127.0.0.1:8765
```

Then **Change project** → paste `<repo>/examples/typescript_demo` with
language **typescript**.

CLI:

```bash
.venv/Scripts/python.exe -m code_constraints.cli parse examples/typescript_demo \
  --lang typescript --out ts_demo.xmi
```

## Limitations vs. the Python / C# demos

The TypeScript parser is syntactic-only (no semantic type resolution across
files), and activity / sequence diagram tags are not yet recognised in
`.ts` files. The demo therefore only exercises the **class** and **package**
diagrams; for activity / sequence walkthroughs, use the Python or C# demo.
