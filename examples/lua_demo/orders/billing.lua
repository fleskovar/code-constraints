--- Billing slice — a hands-on tour of the architectural-rule tags in Lua.
---
--- This is the part of the demo that exercises **`cdec enforce`** (the
--- implementation-conformance engine). Every tag here is *satisfied* except for
--- one clearly-marked, intentional violation in `quick_receipt`, so that:
---
---     cdec enforce examples/lua_demo --lang lua
---
--- prints exactly the two findings explained inline below. Delete that method
--- (or route it through the factory) and the run goes green.
---
--- Lua has no classes and no decorator syntax, so two things differ from the
--- Python and C# demos while meaning exactly the same:
---
--- * **Tags are `---@cdec` comments** placed where a decorator would go. See
---   `cdec_rules.lua` for the vocabulary. The `@cdec` prefix is the namespace,
---   so an unrelated LuaCATS annotation can never be mistaken for a rule.
--- * **A class is a table plus a metatable.** code-constraints promotes a table
---   to a class when it gets methods, an `__index`, a metatable base, or a tag.
---
--- The tags on display:
---
--- * ---@cdec no_instantiation — CheckoutService may not build domain objects.
--- * ---@cdec factory(creates = {...}) — ReceiptFactory is the only place
---   allowed to construct a Receipt.
--- * ---@cdec immutable — a Receipt's fields never change after construction.
--- * ---@cdec sealed — there are no specialised Receipt subtypes.
--- * ---@cdec layer("orders") — assigns these tables to the `orders` layer.
--- * ---@cdec locked — Receipt.formatted's implementation is frozen.

---@cdec immutable
---@cdec sealed
---@cdec layer("orders")
local Receipt = {}
Receipt.__index = Receipt

function Receipt.new(total, lines)
  local self = setmetatable({}, Receipt)
  self.total = total
  self.lines = lines
  return self
end

---@cdec locked(reason = "receipt wording is contractual; finance signed off on it")
function Receipt:formatted()
  -- FROZEN by `cdec lock` (Engine C). The digest of this body is recorded in
  -- `.cdec/locks.yaml`; changing so much as the separator fails `cdec check`.
  -- Try it: swap the em-dash for a comma and re-run
  --     cdec check --config examples/lua_demo --source examples/lua_demo
  -- Reformat it or move the method up the file and nothing happens — the lock
  -- is over the AST, not the text.
  return string.format("%d line(s) — %.2f", self.lines, self.total)
end

---@cdec layer("orders")
local AuditEntry = {}
AuditEntry.__index = AuditEntry

function AuditEntry.new(action)
  local self = setmetatable({}, AuditEntry)
  self.action = action
  return self
end

---@cdec factory(creates = {"Receipt"})
---@cdec layer("orders")
local ReceiptFactory = {}
ReceiptFactory.__index = ReceiptFactory

function ReceiptFactory.new()
  local self = setmetatable({}, ReceiptFactory)
  self.issued = 0
  return self
end

function ReceiptFactory:for_cart(cart)
  self.issued = self.issued + 1
  return Receipt.new(cart:total(), #cart.items) -- OK: this is the factory
end

---@cdec no_instantiation(allow = {"AuditEntry"})
---@cdec layer("orders")
local CheckoutService = {}
CheckoutService.__index = CheckoutService

function CheckoutService.new(receipts)
  local self = setmetatable({}, CheckoutService)
  self.receipts = receipts
  return self
end

function CheckoutService:summarize(cart)
  local audit = AuditEntry.new("summarize")  -- OK: whitelisted via `allow`
  local receipt = self.receipts:for_cart(cart) -- OK: a call, not a construction
  return receipt:formatted() .. " / " .. audit.action
end

function CheckoutService:quick_receipt(cart)
  -- INTENTIONAL VIOLATION — two findings fire on the line below:
  --   [no-instantiation] 'CheckoutService.quick_receipt' constructs 'Receipt'
  --   [factory]          'Receipt' may only be built by ReceiptFactory
  -- Fix by delegating:  return self.receipts:for_cart(cart)
  return Receipt.new(cart:total(), #cart.items)
end

return {
  Receipt = Receipt,
  AuditEntry = AuditEntry,
  ReceiptFactory = ReceiptFactory,
  CheckoutService = CheckoutService,
}
