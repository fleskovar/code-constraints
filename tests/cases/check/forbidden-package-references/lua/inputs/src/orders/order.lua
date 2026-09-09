local Order = {}
Order.__index = Order

function Order.new(id)
  local self = setmetatable({}, Order)
  self.id = id
  return self
end

function Order:total() return 0 end

return Order
