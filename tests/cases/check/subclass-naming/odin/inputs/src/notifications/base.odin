package notifications

// The base does not embed itself, so the rule never examines its name.
Notification :: struct {
	id: string,
}

// `using base: T` is Odin's subtype embedding - it maps to `bases`, not to
// an attribute.
EmailNotifier :: struct {
	using base: Notification,
	address:    string,
}

// The violation: embeds the base, name does not match /.*Notifier$/.
SlackHook :: struct {
	using base: Notification,
	url:        string,
}

// Also breaks the pattern, but is named in `ignore:`.
LegacyPager :: struct {
	using base: Notification,
	number:     string,
}
