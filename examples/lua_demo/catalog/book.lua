---@cdec layer("catalog")
local Author = {}
Author.__index = Author

function Author.new(name, country)
  local self = setmetatable({}, Author)
  self.name = name
  self.country = country
  return self
end

---@cdec layer("catalog")
local Book = {}
Book.__index = Book

function Book.new(title, price, author)
  local self = setmetatable({}, Book)
  self.title = title
  self.price = price
  self.author = author
  return self
end

-- `catalog` is the bottom of the dependency graph: it must not reference
-- `orders`. The `catalog-is-a-leaf-package` rule in .cdec/rules.yaml enforces it.
function Book:display_name()
  return self.title
end

return { Author = Author, Book = Book }
