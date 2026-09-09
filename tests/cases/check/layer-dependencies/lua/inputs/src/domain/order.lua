local SqlRecord = require("infrastructure.record")

-- The violation: `domain: []` allows nothing, and the metatable base is
-- tagged `infrastructure`. A domain type inheriting persistence is the
-- classic layering smell this matrix exists to reject.
---@cdec layer("domain")
local Order = setmetatable({}, { __index = SqlRecord })
Order.__index = Order

function Order:total() return 0 end

return Order
