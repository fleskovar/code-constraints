package orders

// A value object whose invariants cannot survive being extended.
//@cdec sealed
Receipt :: struct {
	total: f64,
}

// Composition instead of embedding: holds a Receipt, does not embed it.
Annotated :: struct {
	receipt: Receipt,
	note:    string,
}

// The violation. `using base: T` is Odin's subtype embedding, and Engine B
// sees through it to the same finding a Python `class D(R)` produces.
Discounted :: struct {
	using base: Receipt,
	pct:        f64,
}
