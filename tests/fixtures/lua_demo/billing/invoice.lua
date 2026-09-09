local Money = require("billing.money")

---@cdec sealed
---@cdec layer("domain")
local Invoice = {}
Invoice.__index = Invoice
Invoice.CURRENCY = "USD"

function Invoice.new(id, total)
  local self = setmetatable({}, Invoice)
  self.id = id
  self.total = total
  self._audit = {}
  return self
end

---@cdec locked(reason = "agreed rounding")
function Invoice:formatted()
  return self.id
end

---@cdec no_instantiation(allow = {"Money"})
function Invoice:summarise(verbose, ...)
  local m = Money.new(0)
  return self.id
end

local Detailed = setmetatable({}, { __index = Invoice })
Detailed.__index = Detailed

function Detailed:note() return self._note end

local function helper(x)
  return x
end

local scratch = {}

return Invoice
