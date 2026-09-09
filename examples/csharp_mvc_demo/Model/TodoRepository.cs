// Model layer — the in-memory store.
//
// Holds the list of TodoItems and exposes the operations the Controller drives.
// It depends only on TodoItem (same layer), so the model package stays a leaf
// in the dependency graph: `layer-dependencies` declares `model: []` — the
// model layer may not reference any other layer.

using System.Collections.Generic;
using CodeConstraints.Rules;

namespace Model;

[Layer("model")]
public class TodoRepository
{
    private readonly List<TodoItem> _items = new List<TodoItem>();

    public IReadOnlyList<TodoItem> Items => _items;

    public void Add(string title)
    {
        _items.Add(new TodoItem(title));
    }

    public void Toggle(int index)
    {
        if (index < 0 || index >= _items.Count)
        {
            return;
        }
        _items[index] = _items[index].WithDone(!_items[index].Done);
    }
}
