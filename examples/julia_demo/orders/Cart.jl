module Carts

using CdecRules

using ..Catalog: Book

@layer "orders" mutable struct Cart
    owner::String
    items::Vector{Book}
end

function total(c::Cart)::Float64
    sum = 0.0
    for item in c.items
        sum += item.price
    end
    return sum
end

function add_item(c::Cart, book::Book)
    push!(c.items, book)
    return c
end

end # module Carts
