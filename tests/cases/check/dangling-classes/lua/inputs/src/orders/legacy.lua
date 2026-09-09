-- Nothing in the project mentions it. Dead code - the violation.
local LegacyPriceTable = {}
LegacyPriceTable.__index = LegacyPriceTable

function LegacyPriceTable:lookup(sku) return 0 end

return LegacyPriceTable
