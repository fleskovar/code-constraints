package orders

import "../catalog"

//@cdec layer("orders")
Cart :: struct {
	items: [dynamic]catalog.Book,
	owner: string,
}

cart_total :: proc(c: ^Cart) -> f64 {
	sum: f64 = 0
	for item in c.items {
		sum += item.price
	}
	return sum
}

add_item :: proc(c: ^Cart, book: catalog.Book) {
	append(&c.items, book)
}
