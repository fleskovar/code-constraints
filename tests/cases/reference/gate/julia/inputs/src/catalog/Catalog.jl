module Catalog

struct Book
    title::String
    rating::Float64
    isbn::String
end

function pages(b::Book, hardback::Bool)::Int
    return 0
end

struct Series
    name::String
end

end
