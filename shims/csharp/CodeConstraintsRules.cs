// No-op architectural-rule attributes for code-constraints.
//
// Reference these to tag classes and methods with architectural constraints.
// They do nothing at runtime — they exist so tagged code compiles, and so the
// UML parser can recognise the tags (it only treats an attribute as a rule when
// the file has `using CodeConstraints.Rules;`). Enforcement happens out-of-band via
// `cdec check` (drift) and `cdec enforce` (implementation conformance).
//
//     using CodeConstraints.Rules;
//
//     [Sealed]
//     [Layer("domain")]
//     public class Order { }
//
//     public class OrderService {
//         [NoInstantiation(Allow = new[] { "List", "Dictionary" })]
//         public decimal Total() => 0m;
//     }

using System;

namespace CodeConstraints.Rules
{
    /// <summary>
    /// Forbid constructing objects in the tagged class/method body.
    /// <c>Allow</c> lists type names that may still be instantiated (e.g.
    /// collections like "List", "Dictionary").
    /// </summary>
    [AttributeUsage(AttributeTargets.Class | AttributeTargets.Method)]
    public sealed class NoInstantiationAttribute : Attribute
    {
        public string[] Allow { get; set; } = Array.Empty<string>();
    }

    /// <summary>
    /// Declare the tagged method free of side effects. <c>Allow</c> carves out
    /// permitted exceptions. (Body analysis is deferred; the tag is still
    /// captured, visualised, and drift-frozen.)
    /// </summary>
    [AttributeUsage(AttributeTargets.Method)]
    public sealed class NoSideEffectsAttribute : Attribute
    {
        public string[] Allow { get; set; } = Array.Empty<string>();
    }

    /// <summary>
    /// Mark the tagged class/method as the designated factory for the types in
    /// <c>Creates</c>; constructing those types anywhere else is forbidden.
    /// </summary>
    [AttributeUsage(AttributeTargets.Class | AttributeTargets.Method)]
    public sealed class FactoryAttribute : Attribute
    {
        public string[] Creates { get; set; } = Array.Empty<string>();
    }

    /// <summary>
    /// Assign the class to an architectural layer, e.g. <c>[Layer("domain")]</c>.
    /// </summary>
    [AttributeUsage(AttributeTargets.Class)]
    public sealed class LayerAttribute : Attribute
    {
        public LayerAttribute(string name) { Name = name; }
        public string Name { get; }
    }

    /// <summary>
    /// Freeze the tagged declaration's implementation. Its normalised syntax
    /// tree is digested into <c>.cdec/locks.yaml</c> by <c>cdec lock set</c>;
    /// any later semantic change — or removal of this attribute — fails
    /// <c>cdec lock check</c>. Reformatting, moving the member, and comment
    /// edits are ignored, because the digest comes from the AST, not the text.
    /// <c>Reason</c> and <c>Owner</c> are recorded in the lockfile.
    /// </summary>
    [AttributeUsage(
        AttributeTargets.Class | AttributeTargets.Struct | AttributeTargets.Interface
        | AttributeTargets.Method | AttributeTargets.Constructor | AttributeTargets.Property)]
    public sealed class LockedAttribute : Attribute
    {
        public string Reason { get; set; } = "";
        public string Owner { get; set; } = "";
    }

    /// <summary>
    /// Forbid subclassing the tagged class.
    /// </summary>
    [AttributeUsage(AttributeTargets.Class)]
    public sealed class SealedAttribute : Attribute { }

    /// <summary>
    /// Forbid reassigning the tagged class's fields after construction.
    /// </summary>
    [AttributeUsage(AttributeTargets.Class)]
    public sealed class ImmutableAttribute : Attribute { }
}
