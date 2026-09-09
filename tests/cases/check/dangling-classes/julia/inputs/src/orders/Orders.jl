module Orders

# Referenced by CheckoutService's `cart` field.
struct Cart
    lines::Int
end

# No incoming references - wired by the application bootstrap. Exempt because
# it is named in `entry_points:`.
struct CheckoutService
    cart::Cart
end

# Nothing in the project mentions it. Dead code - the violation.
struct LegacyPriceTable
    sku::String
end

end
