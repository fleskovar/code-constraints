---@cdec sealed
local AuditEntry = {}
AuditEntry.__index = AuditEntry

function AuditEntry:action() return self._action end

return AuditEntry
