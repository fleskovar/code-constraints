package billing

Money :: struct {
	amount:   f64,
	currency: string,
}

Status :: enum {
	Draft,
	Sent,
	Paid,
}

//@cdec sealed
//@cdec layer("domain")
Invoice :: struct {
	id:     string,
	total:  Money,
	status: Status,
}

Detailed :: struct {
	using base: Invoice,
	note:       string,
}

//@cdec locked(reason = "agreed rounding")
formatted :: proc(inv: ^Invoice) -> string {
	return inv.id
}

//@cdec no_instantiation(allow = ["Money"])
summarise :: proc(inv: ^Invoice, verbose: bool = false) -> (out: string, ok: bool) {
	m := Money{0, "USD"}
	return inv.id, true
}

@(private)
helper :: proc(x: int) -> int {
	return x
}
