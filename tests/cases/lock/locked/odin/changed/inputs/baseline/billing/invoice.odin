package billing

Invoice :: struct {
	id:    string,
	total: f64,
}

//@cdec locked(reason = "invoice wording is contractual")
formatted :: proc(inv: ^Invoice) -> string {
	return inv.id
}
