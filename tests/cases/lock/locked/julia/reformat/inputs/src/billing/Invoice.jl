module Billing

using CdecRules

# An unrelated declaration inserted ABOVE the locked function.
const UNRELATED = 1

struct Invoice
    id::String
end

@locked reason="invoice wording is contractual" function formatted(inv::Invoice)::String
    # a new explanatory comment
    return inv.id
end

end
