package app

// application -> domain: allowed by the matrix.
//@cdec layer("application")
CheckoutHandler :: struct {
	order: domain.Order,
}
