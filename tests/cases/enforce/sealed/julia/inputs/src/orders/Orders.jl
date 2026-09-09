module Orders

using CdecRules

# Julia only allows subtyping an abstract type, so that is where the tag
# earns its keep: it says this hierarchy is closed.
@sealed abstract type Receipt end

# Composition instead of subtyping: holds a Receipt, does not extend it.
struct Annotated
    receipt::Receipt
    note::String
end

# The violation: a sealed type may not be subtyped.
struct Discounted <: Receipt
    pct::Float64
end

end
