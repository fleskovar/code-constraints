package catalog

//@cdec layer("catalog")
Author :: struct {
	name:    string,
	country: string,
}

//@cdec layer("catalog")
Book :: struct {
	title:  string,
	price:  f64,
	author: Author,
}

// `catalog` is the bottom of the dependency graph: it must not reference
// `orders`. The `catalog-is-a-leaf-package` rule in .cdec/rules.yaml enforces it.
display_name :: proc(b: ^Book) -> string {
	return b.title
}
