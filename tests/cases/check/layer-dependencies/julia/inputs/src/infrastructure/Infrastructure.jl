module Infrastructure

using CdecRules

@layer "infrastructure" struct SqlConnection
    dsn::String
end

end
