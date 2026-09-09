package orders

//@cdec immutable
//@cdec sealed
Receipt :: struct {
	total: f64,
}

//@cdec no_side_effects
subtotal :: proc(r: ^Receipt, n: int) -> f64 {
	return r.total
}
