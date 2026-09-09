local Notification = require("notifications.base")

-- The violation: derives from the base, name does not match /.*Notifier$/.
local SlackHook = setmetatable({}, { __index = Notification })
SlackHook.__index = SlackHook

function SlackHook:send(message) end

return SlackHook
