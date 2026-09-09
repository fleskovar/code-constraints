-- An unrelated declaration inserted ABOVE the locked function.
local UNRELATED = 1

local Invoice = {}
Invoice.__index = Invoice

function Invoice.new(id)
  local self = setmetatable({}, Invoice)
  self.id = id
  return self
end

---@cdec locked(reason = "invoice wording is contractual")
function Invoice:formatted()
  -- a new explanatory comment
  return self.id
end

return Invoice
