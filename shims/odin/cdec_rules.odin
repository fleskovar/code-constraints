/*
No-op architectural-rule tags for code-constraints (Odin).

Odin's `@(...)` attributes are a closed set — the compiler rejects any attribute
it does not know ("unknown attribute"), so a no-op `@(cdec_sealed)` would fail to
build. Tags are therefore written as namespaced annotation comments placed
directly above the declaration, in the slot an attribute would occupy. The
`@cdec` prefix is the namespace, so an unrelated comment can never false-match.

	//@cdec sealed
	//@cdec layer("domain")
	Invoice :: struct {
		id:    string,
		total: f64,
	}

	//@cdec no_instantiation(allow = ["Builder"])
	summarise :: proc(inv: ^Invoice) -> string { ... }

	//@cdec locked(reason = "agreed settlement sequence")
	settle :: proc(inv: ^Invoice) -> f64 { ... }

Annotation arguments use call syntax: positional (`layer("domain")`) or named
with `=` (`locked(reason = "why", owner = "ann")`). Lists use brackets:
`no_instantiation(allow = ["Builder"])`. A bare tag needs no parentheses.

Odin has no methods-inside-structs, so code-constraints models a procedure as an
*operation of* a struct when its first parameter is that struct or a pointer to
it (`proc(inv: ^Invoice, ...)`). Tag such a procedure to constrain that operation.

Enforcement happens out-of-band via `cdec check` (drift), `cdec enforce`
(implementation conformance) and `cdec lock` (implementation freeze). The
annotations do nothing at compile time or runtime.

This file additionally declares each tag as a no-op procedure, for code that
prefers an explicit call to a comment, and as the canonical in-repo reference for
the tag vocabulary. The parser reads the annotation comments, not these calls.
*/
package cdec_rules

// Forbid constructing objects in the tagged struct's operations or procedure
// body. Option: `allow` — type names that may still be constructed.
no_instantiation :: proc(subject: rawptr = nil) {}

// Declare the tagged procedure free of side effects. Body analysis is deferred;
// the tag is still captured, visualised and frozen against removal.
no_side_effects :: proc(subject: rawptr = nil) {}

// Forbid embedding the tagged struct as a `using` base (no subtyping).
sealed :: proc(subject: rawptr = nil) {}

// Forbid reassigning the tagged struct's fields after construction.
immutable :: proc(subject: rawptr = nil) {}

// Mark the tagged struct/procedure as the designated constructor of the types in
// `creates`; constructing those types elsewhere is forbidden.
factory :: proc(subject: rawptr = nil) {}

// Freeze the tagged implementation. `cdec lock set` records the element's
// normalised AST digest in `.cdec/locks.yaml`; any later semantic change to the
// body — or removal of the tag — fails `cdec lock check`. Reformatting, moving
// the declaration, and editing comments do not trip the lock.
// Options: `reason`, `owner`.
locked :: proc(subject: rawptr = nil) {}

// Assign the struct to an architectural layer for dependency-direction checks.
layer :: proc(subject: rawptr = nil) {}
