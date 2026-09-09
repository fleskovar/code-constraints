local Series = {}
Series.__index = Series

function Series:name() return self._name end

return Series
