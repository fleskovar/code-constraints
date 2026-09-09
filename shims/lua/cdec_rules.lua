--- No-op architectural-rule tags for code-constraints (Lua).
---
--- Lua has no decorator or attribute syntax, so tags are written as namespaced
--- annotation comments placed directly above the declaration — the slot a
--- Python decorator would occupy. The `@cdec` prefix is the namespace, so an
--- unrelated LuaCATS/LuaLS annotation can never be mistaken for a rule.
---
---     local Invoice = {}
---     Invoice.__index = Invoice
---
---     ---@cdec sealed
---     ---@cdec layer("domain")
---     local Invoice = {}
---
---     ---@cdec no_instantiation(allow = {"table"})
---     function Invoice:summarise() end
---
---     ---@cdec locked(reason = "agreed settlement sequence")
---     function Invoice:settle() end
---
--- Annotation arguments use Lua call syntax: positional (`layer("domain")`),
--- or named with `=` (`locked(reason = "why", owner = "ann")`). Lists are Lua
--- tables: `no_instantiation(allow = {"table", "string"})`. A bare tag needs no
--- parentheses (`---@cdec sealed`).
---
--- code-constraints treats a table that gets methods (`function T:m()` /
--- `function T.m()`) or an `__index` metatable as a class; `self.x = ...` in the
--- constructor becomes its attributes; `setmetatable(T, { __index = Base })`
--- becomes inheritance.
---
--- Enforcement happens out-of-band via `cdec check` (drift), `cdec enforce`
--- (implementation conformance) and `cdec lock` (implementation freeze). The
--- annotations do nothing at runtime.
---
--- This module additionally exposes each tag as a runtime no-op function, for
--- code that prefers an explicit call to a comment. The parser reads the
--- annotation comments, not these calls — the functions exist so that
--- `require("cdec_rules")` resolves and tagged code keeps running.

local cdec = {}

--- Identity: every tag returns its subject unchanged.
--- @generic T
--- @param subject T
--- @return T
local function passthrough(subject)
  return subject
end

--- Forbid constructing objects in the tagged table's methods or function body.
--- Options: `allow` (table of type names that may still be constructed).
function cdec.no_instantiation(subject, _opts)
  return passthrough(subject)
end

--- Declare the tagged function free of side effects. Body analysis is deferred;
--- the tag is still captured, visualised and frozen against removal.
function cdec.no_side_effects(subject, _opts)
  return passthrough(subject)
end

--- Forbid using the tagged table as a metatable `__index` base (no subclassing).
function cdec.sealed(subject)
  return passthrough(subject)
end

--- Forbid reassigning the tagged table's fields after construction.
function cdec.immutable(subject)
  return passthrough(subject)
end

--- Mark the tagged table/function as the designated constructor of the types in
--- `creates`; constructing those types elsewhere is forbidden.
function cdec.factory(subject, _opts)
  return passthrough(subject)
end

--- Freeze the tagged implementation. `cdec lock set` records the element's
--- normalised AST digest in `.cdec/locks.yaml`; any later semantic change to the
--- body — or removal of the tag — fails `cdec lock check`. Reformatting, moving
--- the element, and editing comments do not trip the lock.
--- Options: `reason`, `owner`.
function cdec.locked(subject, _opts)
  return passthrough(subject)
end

--- Assign the table to an architectural layer for dependency-direction checks.
function cdec.layer(subject, _name)
  return passthrough(subject)
end

return cdec
