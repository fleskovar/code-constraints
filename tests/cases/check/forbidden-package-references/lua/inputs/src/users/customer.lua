-- In `to:` but never referenced from catalog.
local Customer = {}
Customer.__index = Customer

function Customer:email() return self._email end

return Customer
