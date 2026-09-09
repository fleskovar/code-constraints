local models = require("orders.models")
local Receipt = models.Receipt
local AuditEntry = models.AuditEntry

-- An orchestrator: it wires collaborators together, it does not build them.
---@cdec no_instantiation(allow = {"AuditEntry"})
local CheckoutService = {}
CheckoutService.__index = CheckoutService

-- Allowed by name.
function CheckoutService:checkout()
  return AuditEntry.new("checkout")
end

-- The violation: `Receipt` is not in `allow`.
function CheckoutService:quick_receipt(total)
  return Receipt.new(total)
end

return CheckoutService
