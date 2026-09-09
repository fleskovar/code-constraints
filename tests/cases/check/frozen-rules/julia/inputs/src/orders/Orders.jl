module Orders

using CdecRules

# `@sealed` deleted. `@immutable` survives untouched.
@immutable struct Receipt
    total::Float64
end

# `@no_side_effects` deleted from an *operation*. A Julia function's owner is
# the type of its first parameter, so this tag sat on `Receipt.subtotal`.
function subtotal(r::Receipt, n::Int)::Float64
    return r.total
end

end
