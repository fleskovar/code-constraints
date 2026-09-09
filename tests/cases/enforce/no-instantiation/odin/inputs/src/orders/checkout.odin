package orders

Receipt :: struct {
	total: f64,
}

AuditEntry :: struct {
	action: string,
}

// An orchestrator: it wires collaborators together, it does not build them.
//@cdec no_instantiation(allow = ["AuditEntry"])
CheckoutService :: struct {
	seq: int,
}

// Allowed by name.
checkout :: proc(c: ^CheckoutService) -> AuditEntry {
	return AuditEntry{"checkout"}
}

// The violation: `Receipt` is not in `allow`.
quick_receipt :: proc(c: ^CheckoutService, total: f64) -> Receipt {
	return Receipt{total}
}
