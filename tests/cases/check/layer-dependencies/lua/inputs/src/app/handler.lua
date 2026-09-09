local Order = require("domain.order")

-- application -> domain: allowed by the matrix.
---@cdec layer("application")
local CheckoutHandler = setmetatable({}, { __index = Order })
CheckoutHandler.__index = CheckoutHandler

function CheckoutHandler:handle() end

return CheckoutHandler
