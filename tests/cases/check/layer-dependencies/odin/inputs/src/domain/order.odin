package domain

// The violation: `domain: []` allows nothing, and SqlConnection is tagged
// `infrastructure`. The `Logger` field is invisible - Logger carries no
// `@cdec layer` tag, and the rule cannot reason about untagged targets.
//@cdec layer("domain")
Order :: struct {
	id:   string,
	conn: infrastructure.SqlConnection,
	log:  support.Logger,
}
