package orders

// orders -> catalog: the permitted direction. `from:` names catalog only.
Order :: struct {
	id:   string,
	item: catalog.Book,
}
