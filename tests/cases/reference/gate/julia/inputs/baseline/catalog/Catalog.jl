module Catalog

struct Book
    title::String
    rating::Int
end

function pages(b::Book)::Int
    return 0
end

end
