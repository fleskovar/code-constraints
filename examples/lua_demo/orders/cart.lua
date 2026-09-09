---@cdec layer("orders")
local Cart = {}
Cart.__index = Cart

function Cart.new(owner)
  local self = setmetatable({}, Cart)
  self.owner = owner
  self.items = {}
  return self
end

function Cart:add_item(book)
  table.insert(self.items, book)
end

function Cart:total()
  local sum = 0
  for _, item in ipairs(self.items) do
    sum = sum + item.price
  end
  return sum
end

return Cart
