package orders

//@cdec immutable
Receipt :: struct {
	total: f64,
	lines: int,
}

// Returns a new value instead of mutating. A composite literal is a
// construction, not an assignment to the receiver, so this is silent.
with_discount :: proc(r: ^Receipt, pct: f64) -> Receipt {
	return Receipt{r.total * (1 - pct), r.lines}
}

// Reads only. Silent.
formatted :: proc(r: ^Receipt) -> f64 {
	return r.total
}

// The violation: an assignment whose target is a member expression rooted at
// the receiver parameter.
apply_discount :: proc(r: ^Receipt, pct: f64) {
	r.total = r.total * (1 - pct)
}
