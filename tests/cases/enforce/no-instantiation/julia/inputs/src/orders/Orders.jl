module Orders

using CdecRules

struct Receipt
    total::Float64
end

struct AuditEntry
    action::String
end

# An orchestrator: it wires collaborators together, it does not build them.
@no_instantiation allow=["AuditEntry"] struct CheckoutService
    seq::Int
end

# Allowed by name.
function checkout(c::CheckoutService)::AuditEntry
    return AuditEntry("checkout")
end

# The violation: `Receipt` is not in `allow`.
function quick_receipt(c::CheckoutService, total::Float64)::Receipt
    return Receipt(total)
end

end
