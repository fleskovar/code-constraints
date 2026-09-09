local Book = require("catalog.book")

-- catalog -> catalog. A self-edge is dropped before the rule sees it.
local Paperback = setmetatable({}, { __index = Book })
Paperback.__index = Paperback

function Paperback:weight() return 0 end

return Paperback
