// Controller layer — the input-handling contract.
//
// Marker interface mirroring IView. Tagged [Layer("controller")] so it sits in
// the top layer, and used as the `base` of the `subclass-naming` rule: every
// implementer must end in `Controller`.

using CodeConstraints.Rules;

namespace Controller;

[Layer("controller")]
public interface IController
{
    void Handle(string command);
}
