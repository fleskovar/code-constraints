// Model layer — the domain entity.
//
// A TodoItem is a small immutable value: once created its fields never change
// (toggling "done" produces a new instance, see WithDone). That makes it a
// natural showcase for two implementation-conformance tags that `cdec enforce`
// verifies:
//   * [Immutable] — get-only properties, assigned only in the constructor.
//   * [Sealed]    — no specialised TodoItem subtypes.
// [Layer("model")] places it at the bottom of the dependency graph: nothing in
// this file references View or Controller, and the `layer-dependencies` rule
// forbids it from ever doing so.

using CodeConstraints.Rules;

namespace Model;

[Immutable]
[Sealed]
[Layer("model")]
public class TodoItem
{
    public string Title { get; }
    public bool Done { get; }

    public TodoItem(string title, bool done = false)
    {
        Title = title;
        Done = done;
    }

    // Immutable-clean: returns a new instance rather than mutating this one.
    public TodoItem WithDone(bool done) => new TodoItem(Title, done);
}
