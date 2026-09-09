---@cdec layer("infrastructure")
local SqlRecord = {}
SqlRecord.__index = SqlRecord

function SqlRecord:save() end

return SqlRecord
