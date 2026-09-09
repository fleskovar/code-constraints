---@cdec immutable
local Receipt = {}
Receipt.__index = Receipt

-- `new` is one of the recognised constructor names, so `self.x = ...` here is
-- initialisation, not reassignment.
function Receipt.new(total, lines)
  local self = setmetatable({}, Receipt)
  self.total = total
  self.lines = lines
  return self
end

-- Returns a new instance instead of mutating. Silent.
function Receipt:with_discount(pct)
  return Receipt.new(self.total * (1 - pct), self.lines)
end

-- Reads only. Silent.
function Receipt:formatted()
  return self.lines
end

-- The violation: `self.x = ...` outside the constructor.
function Receipt:apply_discount(pct)
  self.total = self.total * (1 - pct)
end

return Receipt
