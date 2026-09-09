local Receipt = {}
Receipt.__index = Receipt

function Receipt.new(total)
  local self = setmetatable({}, Receipt)
  self.total = total
  return self
end

local AuditEntry = {}
AuditEntry.__index = AuditEntry

function AuditEntry.new(action)
  local self = setmetatable({}, AuditEntry)
  self.action = action
  return self
end

return { Receipt = Receipt, AuditEntry = AuditEntry }
