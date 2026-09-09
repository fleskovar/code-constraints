package orders

// No incoming references - wired by the application bootstrap. Exempt
// because it is named in `entry_points:`.
CheckoutService :: struct {
	cart: Cart,
}
