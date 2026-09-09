local Order = require("orders.order")

-- catalog -> orders. In Lua a metatable base is the reference the model can
-- see: fields carry no type annotation, so an attribute never resolves.
local Book = setmetatable({}, { __index = Order })
Book.__index = Book

function Book.new(title)
  local self = setmetatable({}, Book)
  self.title = title
  return self
end

function Book:describe() return self.title end

return Book
