local Service = require("orders.service")

-- No incoming references - wired by the application bootstrap. Exempt
-- because it is named in `entry_points:`.
local CheckoutService = setmetatable({}, { __index = Service })
CheckoutService.__index = CheckoutService

function CheckoutService:checkout() end

return CheckoutService
