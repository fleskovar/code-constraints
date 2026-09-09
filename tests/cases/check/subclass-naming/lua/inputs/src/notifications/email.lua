local Notification = require("notifications.base")

local EmailNotifier = setmetatable({}, { __index = Notification })
EmailNotifier.__index = EmailNotifier

function EmailNotifier:send(message) end

return EmailNotifier
