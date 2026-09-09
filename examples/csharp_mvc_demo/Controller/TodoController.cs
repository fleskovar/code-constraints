// Controller layer — the coordinator.
//
// The Controller is the only layer allowed to know about both the Model and the
// View: `controller: [model, view]` in the allow-matrix. It receives both
// collaborators by constructor injection and stores them as typed fields —
//   * TodoRepository _repo  -> the "controller -> model" edge
//   * IView          _view  -> the "controller -> view" edge
// both of which `layer-dependencies` sees and permits.
//
// In a real app a composition root (e.g. Program.Main) would `new` these up and
// hand them to the controller; that wiring is the one place construction is
// expected to happen, and it lives above all three layers.

using Model;
using View;
using CodeConstraints.Rules;

namespace Controller;

[Layer("controller")]
public class TodoController : IController
{
    private readonly TodoRepository _repo;
    private readonly IView _view;

    public TodoController(TodoRepository repo, IView view)
    {
        _repo = repo;
        _view = view;
    }

    public void Handle(string command)
    {
        var parts = command.Split(' ', 2);
        switch (parts[0])
        {
            case "add" when parts.Length > 1:
                _repo.Add(parts[1]);
                break;
            case "toggle" when parts.Length > 1 && int.TryParse(parts[1], out var index):
                _repo.Toggle(index);
                break;
        }
        _view.Render();
    }
}
