---@cdec sealed
local Receipt = {}
Receipt.__index = Receipt

function Receipt.new(total)
  local self = setmetatable({}, Receipt)
  self.total = total
  return self
end

return Receipt
