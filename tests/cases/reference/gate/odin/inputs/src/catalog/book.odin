package catalog

Book :: struct {
	title:  string,
	rating: f64,
	isbn:   string,
}

pages :: proc(b: ^Book, hardback: bool) -> int {
	return 0
}

Series :: struct {
	name: string,
}
