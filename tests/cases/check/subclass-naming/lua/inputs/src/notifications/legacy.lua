local Notification = require("notifications.base")

-- Also breaks the pattern, but is named in `ignore:`.
local LegacyPager = setmetatable({}, { __index = Notification })
LegacyPager.__index = LegacyPager

function LegacyPager:send(message) end

return LegacyPager
