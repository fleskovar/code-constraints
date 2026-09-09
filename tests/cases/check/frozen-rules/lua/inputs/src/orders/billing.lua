-- `---@cdec sealed` deleted. `immutable` survives untouched.
---@cdec immutable
local Receipt = {}
Receipt.__index = Receipt

-- `---@cdec no_side_effects` deleted from an *operation*.
function Receipt:subtotal(n) return self.total end

return Receipt
