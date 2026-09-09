module App

using CdecRules

# application -> domain: allowed by the matrix.
@layer "application" struct CheckoutHandler
    order::Order
end

end
