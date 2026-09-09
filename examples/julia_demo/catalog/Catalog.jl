module Catalog

using CdecRules

@layer "catalog" struct Author
    name::String
    country::String
end

@layer "catalog" struct Book
    title::String
    price::Float64
    author::Author
end

# `catalog` is the bottom of the dependency graph: it must not reference
# `orders`. The `catalog-is-a-leaf-package` rule in .cdec/rules.yaml enforces it.
display_name(b::Book)::String = b.title

end # module Catalog
