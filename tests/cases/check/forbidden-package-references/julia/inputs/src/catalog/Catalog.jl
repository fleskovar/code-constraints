module Catalog

# catalog.Catalog -> orders.Orders. The forbidden edge: a field type.
struct Book
    title::String
    reserved::Order
end

# A self-edge inside catalog.Catalog is dropped before the rule sees it.
struct Author
    name::String
    work::Book
end

end
