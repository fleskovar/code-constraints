module Billing

using CdecRules

abstract type AbstractInvoice end

struct Money
    amount::Float64
    currency::String
end

@sealed @layer "domain" struct Invoice <: AbstractInvoice
    id::String
    total::Money

    Invoice(id) = new(id, Money(0.0, "USD"))
end

mutable struct Draft
    lines::Vector{String}
end

@locked reason="agreed rounding" function formatted(inv::Invoice)::String
    return inv.id
end

@no_instantiation allow=["Money"] function summarise(inv::Invoice, verbose::Bool=false; short=true)
    m = Money(0.0, "USD")
    return inv.id
end

total_of(inv::Invoice) = inv.total

helper(x::Int) = x + 1

end # module
