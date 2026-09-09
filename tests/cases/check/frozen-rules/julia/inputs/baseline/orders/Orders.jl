module Orders

using CdecRules

@immutable @sealed struct Receipt
    total::Float64
end

@no_side_effects function subtotal(r::Receipt, n::Int)::Float64
    return r.total
end

end
