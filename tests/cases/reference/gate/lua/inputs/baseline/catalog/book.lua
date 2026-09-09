local Book = {}
Book.__index = Book

function Book.new(title)
  local self = setmetatable({}, Book)
  self.title = title
  self.rating = 0
  return self
end

function Book:pages() return 0 end

return Book
