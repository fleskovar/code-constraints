local Receipt = require("orders.receipt")

-- Composition instead of inheritance: holds a Receipt, does not derive from
-- it. `Receipt.new` inside a constructor is construction, not subtyping.
local Annotated = {}
Annotated.__index = Annotated

function Annotated.new(receipt, note)
  local self = setmetatable({}, Annotated)
  self.receipt = receipt
  self.note = note
  return self
end

return Annotated
