module Orders

using CdecRules

struct Receipt
    total::Float64
end

# The designated constructor. Construction is permitted anywhere inside the
# owning type, so this is silent.
@factory creates=["Receipt"] struct ReceiptFactory
    seq::Int
end

function for_total(f::ReceiptFactory, total::Float64)::Receipt
    return Receipt(total)
end

struct CheckoutService
    seq::Int
end

# The violation: `Receipt(...)` outside its designated factory. In Julia a
# call counts as construction only when its callee is a type this parse saw.
function quick_receipt(c::CheckoutService, total::Float64)::Receipt
    return Receipt(total)
end

end
