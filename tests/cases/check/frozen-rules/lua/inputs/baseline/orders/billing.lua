---@cdec immutable
---@cdec sealed
local Receipt = {}
Receipt.__index = Receipt

---@cdec no_side_effects
function Receipt:subtotal(n) return self.total end

return Receipt
