module Billing

using CdecRules

struct Invoice
    id::String
end

@locked reason="invoice wording is contractual" function formatted(inv::Invoice)::String
    return inv.id * "!"
end

end
