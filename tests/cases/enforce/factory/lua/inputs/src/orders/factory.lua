local Receipt = require("orders.receipt")

-- The designated constructor. Construction is permitted anywhere inside the
-- owning class, so this is silent.
---@cdec factory(creates = {"Receipt"})
local ReceiptFactory = {}
ReceiptFactory.__index = ReceiptFactory

function ReceiptFactory:for_total(total)
  return Receipt.new(total)
end

return ReceiptFactory
