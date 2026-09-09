module Notifications

# Julia subtyping is `<: Abstract`. The abstract type itself has no
# supertype here, so the rule never examines its name.
abstract type Notification end

struct EmailNotifier <: Notification
    address::String
end

# The violation: subtypes the base, name does not match /.*Notifier$/.
struct SlackHook <: Notification
    url::String
end

# Also breaks the pattern, but is named in `ignore:`.
struct LegacyPager <: Notification
    number::String
end

end
