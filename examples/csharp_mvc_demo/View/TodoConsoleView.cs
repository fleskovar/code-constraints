// View layer — a concrete console renderer.
//
// Reads model state and turns it into output. It holds a TodoRepository as a
// constructor-injected field, which is what makes the "view -> model" edge
// visible to `layer-dependencies` (the rule only sees dependencies expressed as
// typed fields or inheritance, never method-body locals). `view: [model]` in
// the allow-matrix permits exactly this edge.
//
// The class name ends in `View`, satisfying the `subclass-naming` rule for
// implementers of IView.

using System;
using Model;
using CodeConstraints.Rules;

namespace View;

[Layer("view")]
public class TodoConsoleView : IView
{
    private readonly TodoRepository _repo;

    public TodoConsoleView(TodoRepository repo)
    {
        _repo = repo;
    }

    public void Render()
    {
        for (int i = 0; i < _repo.Items.Count; i++)
        {
            var item = _repo.Items[i];
            var box = item.Done ? "[x]" : "[ ]";
            Console.WriteLine($"{i}. {box} {item.Title}");
        }
    }
}
