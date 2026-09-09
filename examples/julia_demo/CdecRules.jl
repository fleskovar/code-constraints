"""
No-op architectural-rule macros for code-constraints.

Bring these into scope to tag structs and functions with architectural
constraints. Every macro expands to its decorated definition unchanged — they
exist so tagged code still loads and runs, and so the UML parser can recognise
the tags (a `@macro` only counts as a rule when the file brings `CdecRules`
into scope). Enforcement happens out-of-band via `cdec check` (drift),
`cdec enforce` (implementation conformance) and `cdec lock` (implementation
freeze).

    using CdecRules

    @sealed @layer "domain" struct Invoice
        id::String
        total::Float64
    end

    @no_instantiation allow=["Dict"] function summarise(inv::Invoice)
        ...
    end

    @locked reason="agreed settlement sequence" function settle(inv::Invoice)
        ...
    end

Julia has no methods-inside-structs, so code-constraints models a function as an
*operation of* a struct when its first argument is annotated with that struct's
type (`f(inv::Invoice, ...)`). Tag such a function to constrain that operation.

Argument forms
--------------
Julia macros take their arguments space-separated, not parenthesised:

    @layer "domain" struct Order end        # positional
    @locked reason="why" function f() end   # keyword
    @layer("domain") struct Order end       # WRONG — a syntax error in Julia

Every macro here is variadic and returns its final argument, so stacking works
in any order and unknown extra arguments are ignored rather than erroring.
"""
module CdecRules

export @no_instantiation, @no_side_effects, @sealed, @immutable
export @factory, @locked, @layer

# Every tag is a pass-through: the decorated definition is the last argument
# (Julia nests stacked macros, so `@sealed @layer "x" struct ... end` reaches
# this macro as a single nested macrocall that expands in turn).
macro _passthrough(args...)
    return esc(args[end])
end

"""
    @no_instantiation [allow=[...]] <definition>

Forbid constructing objects in the tagged struct's operations or function body.
`allow` lists type names that may still be constructed (e.g. `["Dict", "Vector"]`).
"""
macro no_instantiation(args...)
    return esc(args[end])
end

"""
    @no_side_effects [allow=[...]] <function>

Declare the tagged function free of side effects. Body analysis is deferred; the
tag is captured, visualised and frozen against removal by `cdec check`.
"""
macro no_side_effects(args...)
    return esc(args[end])
end

"""
    @sealed <struct>

Forbid subtyping the tagged type (composition over inheritance). Applies to
`abstract type` declarations, where Julia subtyping is actually possible.
"""
macro sealed(args...)
    return esc(args[end])
end

"""
    @immutable <struct>

Forbid reassigning the tagged struct's fields after construction. A plain
`struct` is already immutable in Julia; the tag is meaningful on
`mutable struct`, where it says the mutability is an implementation detail that
operations may not use.
"""
macro immutable(args...)
    return esc(args[end])
end

"""
    @factory creates=["T", ...] <definition>

Mark the tagged struct or function as the designated constructor of the types in
`creates`; constructing those types anywhere else is forbidden.
"""
macro factory(args...)
    return esc(args[end])
end

"""
    @locked [reason="..."] [owner="..."] <definition>

Freeze the tagged implementation. The element's normalised AST is digested and
recorded in `.cdec/locks.yaml` by `cdec lock set`. Any later semantic change to
the body — or removal of this tag — fails `cdec lock check`. Moving the element,
reformatting it, or editing comments does not trip the lock: the digest comes
from the AST, not the source text.
"""
macro locked(args...)
    return esc(args[end])
end

"""
    @layer "name" <struct>

Assign the type to an architectural layer for dependency-direction checks
(`cdec check`'s `layer-dependencies` rule).
"""
macro layer(args...)
    return esc(args[end])
end

end # module CdecRules
