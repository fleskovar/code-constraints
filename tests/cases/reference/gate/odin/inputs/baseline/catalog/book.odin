package catalog

Book :: struct {
	title:  string,
	rating: int,
}

pages :: proc(b: ^Book) -> int {
	return 0
}
