-- The base is not derived from itself, so it is never examined.
local Notification = {}
Notification.__index = Notification

function Notification:send(message) end

return Notification
