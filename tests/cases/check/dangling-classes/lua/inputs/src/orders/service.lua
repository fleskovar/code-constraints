-- Referenced as CheckoutService's metatable base, so it has an incoming edge.
local Service = {}
Service.__index = Service

function Service:run() end

return Service
