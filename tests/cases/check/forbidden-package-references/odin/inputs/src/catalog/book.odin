package catalog

// catalog -> orders. The forbidden edge: a cross-package field type.
Book :: struct {
	title:    string,
	reserved: orders.Order,
}

// catalog -> catalog. A self-edge is dropped before the rule sees it.
Author :: struct {
	name: string,
	work: Book,
}
