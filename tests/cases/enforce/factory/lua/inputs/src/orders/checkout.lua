local Receipt = require("orders.receipt")

local CheckoutService = {}
CheckoutService.__index = CheckoutService

-- Delegates construction. Silent.
function CheckoutService:checkout(total)
  return self.receipts:for_total(total)
end

-- The violation: `T.new(...)` outside the designated factory. A bare
-- `Receipt(...)` would NOT count - in Lua that is `__call`, not a constructor.
function CheckoutService:quick_receipt(total)
  return Receipt.new(total)
end

return CheckoutService
