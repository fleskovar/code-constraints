module Domain

using CdecRules

# The violation: `domain: []` allows nothing, and SqlConnection is tagged
# `infrastructure`. The `Logger` field is invisible - Logger carries no
# `@layer` macro, and the rule cannot reason about untagged targets.
@layer "domain" struct Order
    id::String
    conn::SqlConnection
    log::Logger
end

end
