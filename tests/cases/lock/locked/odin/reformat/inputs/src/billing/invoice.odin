package billing

// An unrelated declaration inserted ABOVE the locked proc.
UNRELATED :: 1

Invoice :: struct {
	id:    string,
	total: f64,
}

// NOTE: no trailing comma after the parameter. `odin-ts/1` serialises
// anonymous tokens (it must, or `a + b` and `a - b` would hash alike), and a
// trailing comma is one - so adding one DOES move the digest. See the README.
//@cdec locked(reason = "invoice wording is contractual")
formatted :: proc(
	inv: ^Invoice
) -> string {
	// a new explanatory comment
	return inv.id
}
