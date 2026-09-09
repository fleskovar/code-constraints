local Invoice = {}
Invoice.__index = Invoice

function Invoice.new(id)
  local self = setmetatable({}, Invoice)
  self.id = id
  return self
end

---@cdec locked(reason = "invoice wording is contractual")
function Invoice:formatted()
  return self.id
end

return Invoice
