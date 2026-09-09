package orders

Receipt :: struct {
	total: f64,
}

// The designated constructor. Construction is permitted anywhere inside the
// owning type, so this is silent.
//@cdec factory(creates = ["Receipt"])
ReceiptFactory :: struct {
	seq: int,
}

for_total :: proc(f: ^ReceiptFactory, total: f64) -> Receipt {
	return Receipt{total}
}

CheckoutService :: struct {
	seq: int,
}

// The violation: a composite literal for `Receipt` outside its factory.
quick_receipt :: proc(c: ^CheckoutService, total: f64) -> Receipt {
	return Receipt{total}
}
