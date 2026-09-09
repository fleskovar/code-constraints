package orders

// `@cdec sealed` deleted. `@cdec immutable` survives, so only one class-level
// tag fires.
//@cdec immutable
Receipt :: struct {
	total: f64,
}

// `@cdec no_side_effects` deleted from an *operation*. The proc's owner is the
// type of its first parameter, so this tag sits on `orders.Receipt.subtotal`.
subtotal :: proc(r: ^Receipt, n: int) -> f64 {
	return r.total
}
