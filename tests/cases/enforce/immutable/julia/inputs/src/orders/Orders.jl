module Orders

using CdecRules

# A non-`mutable` struct is already immutable to the compiler. The tag earns
# its keep on a `mutable struct`, where it says the mutability is an
# implementation detail rather than part of the contract.
@immutable mutable struct Receipt
    total::Float64
    lines::Int
end

# Returns a new value instead of mutating. Silent.
function with_discount(r::Receipt, pct::Float64)::Receipt
    return Receipt(r.total * (1 - pct), r.lines)
end

# Reads only. Silent.
function formatted(r::Receipt)::Int
    return r.lines
end

# The violation: an assignment whose target is a field expression rooted at
# the receiver argument.
function apply_discount(r::Receipt, pct::Float64)
    r.total = r.total * (1 - pct)
end

end
