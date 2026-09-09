local Receipt = require("orders.receipt")

-- The violation. An `__index` metatable is Lua's inheritance, and Engine B
-- sees through it to the same finding a Python `class D(R)` produces.
local Discounted = setmetatable({}, { __index = Receipt })
Discounted.__index = Discounted

function Discounted:pct() return self._pct end

return Discounted
