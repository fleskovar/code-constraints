// View layer — the rendering contract.
//
// Marker interface so the Controller can depend on the *view abstraction*
// rather than a concrete renderer. Two rules lean on it:
//   * [Layer("view")]   — gives the interface a layer, so `layer-dependencies`
//                         can see "controller -> view" when the Controller holds
//                         an IView field (targets without a layer tag are
//                         ignored by that rule).
//   * `subclass-naming` — every class implementing IView must end in `View`.

using CodeConstraints.Rules;

namespace View;

[Layer("view")]
public interface IView
{
    void Render();
}
