local Book = {}
Book.__index = Book

function Book.new(title)
  local self = setmetatable({}, Book)
  self.title = title
  self.isbn = ""
  return self
end

function Book:pages(hardback) return 0 end

function Book:reprint() end

return Book
