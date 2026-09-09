"""Language-agnostic UML data model.

All parsers (Python AST, C# tree-sitter) produce a `Project`; all consumers
(XMI writer, DOT emitter, diff engine) operate on `Project`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha1
from typing import Iterator, Literal, get_args


class DiffStatus(str, Enum):
    UNCHANGED = "unchanged"
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"


class Visibility(str, Enum):
    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"
    PACKAGE = "package"


ClassKind = Literal["class", "interface", "abstract", "enum", "struct", "record", "static"]
ActivityNodeKind = Literal[
    "initial", "final", "action", "decision", "merge", "fork", "join"
]


@dataclass
class SourceLocation:
    file: str
    start_line: int
    end_line: int


@dataclass
class Layout:
    """Optional persisted canvas layout for an element. `None` means the
    renderer should auto-place the element. Coordinates are in canvas units
    (pixels) with origin at top-left."""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    collapsed: bool = False


@dataclass
class EdgeLayout:
    """Per-edge layout: a list of waypoints the edge routes through, in canvas
    units. Empty means the renderer routes the edge itself."""
    waypoints: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class RuleAnnotation:
    """An architectural-rule tag attached to a Class or Operation.

    `name` is the canonical catalog id (e.g. "no-instantiation"). `args` and
    `kwargs` hold the decorator/attribute argument *source text* so the value
    round-trips verbatim and dataclass equality gives exact diff comparison."""
    name: str
    args: list[str] = field(default_factory=list)
    kwargs: dict[str, str] = field(default_factory=dict)


@dataclass
class Parameter:
    name: str
    type: str = ""
    default: str | None = None

    def signature(self) -> str:
        return f"{self.name}:{self.type}"


@dataclass
class Attribute:
    name: str
    type: str = ""
    visibility: Visibility = Visibility.PUBLIC
    is_static: bool = False
    is_readonly: bool = False
    default: str | None = None
    description: str | None = None
    status: DiffStatus = DiffStatus.UNCHANGED

    def signature(self) -> str:
        return f"{self.name}:{self.type}"


@dataclass
class Operation:
    name: str
    parameters: list[Parameter] = field(default_factory=list)
    return_type: str = ""
    visibility: Visibility = Visibility.PUBLIC
    is_static: bool = False
    is_abstract: bool = False
    description: str | None = None
    rules: list[RuleAnnotation] = field(default_factory=list)
    status: DiffStatus = DiffStatus.UNCHANGED

    def signature(self) -> str:
        params = ",".join(p.signature() for p in self.parameters)
        return f"{self.name}({params}):{self.return_type}"


@dataclass
class Class:
    name: str
    qualified_name: str
    kind: ClassKind = "class"
    attributes: list[Attribute] = field(default_factory=list)
    operations: list[Operation] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    location: SourceLocation | None = None
    layout: Layout | None = None
    description: str | None = None
    rules: list[RuleAnnotation] = field(default_factory=list)
    status: DiffStatus = DiffStatus.UNCHANGED
    # Raw type-name strings referenced inside method bodies (no type
    # resolution). Consumers resolve these via `associations.resolve_association`
    # to draw "uses" edges and count incoming references. Empty for pre-existing
    # XMI and for parsers that don't scan bodies.
    dependencies: list[str] = field(default_factory=list)

    def stable_id(self) -> str:
        return _stable_id("Class", self.qualified_name)


@dataclass
class Package:
    name: str
    qualified_name: str
    classes: list[Class] = field(default_factory=list)
    sub_packages: list[Package] = field(default_factory=list)
    layout: Layout | None = None
    description: str | None = None
    status: DiffStatus = DiffStatus.UNCHANGED

    def stable_id(self) -> str:
        return _stable_id("Package", self.qualified_name)


@dataclass
class ActivityNode:
    id: str
    kind: ActivityNodeKind
    label: str = ""
    layout: Layout | None = None
    status: DiffStatus = DiffStatus.UNCHANGED


@dataclass
class ActivityEdge:
    source: str
    target: str
    guard: str = ""
    edge_layout: EdgeLayout | None = None
    status: DiffStatus = DiffStatus.UNCHANGED


@dataclass
class Activity:
    name: str
    nodes: list[ActivityNode] = field(default_factory=list)
    edges: list[ActivityEdge] = field(default_factory=list)
    location: SourceLocation | None = None
    granularity: Literal["control-flow", "statement", "calls"] = "control-flow"
    status: DiffStatus = DiffStatus.UNCHANGED

    def stable_id(self) -> str:
        return _stable_id("Activity", self.name)


@dataclass
class Lifeline:
    name: str
    represents: str = ""  # type name the lifeline represents
    column_x: float | None = None  # canvas-units; None = auto-layout
    status: DiffStatus = DiffStatus.UNCHANGED


@dataclass
class Message:
    sender: str  # lifeline name
    receiver: str
    label: str
    is_return: bool = False
    # Optional guard condition, e.g. "result == 'ok'" — set by the parser when
    # the call sits inside an `if` branch so the renderer can prefix the
    # message label with `[guard]` (UML combined-fragment shorthand).
    guard: str = ""
    status: DiffStatus = DiffStatus.UNCHANGED


@dataclass
class Fragment:
    """A UML combined fragment covering a contiguous range of message rows.

    `start_row` and `end_row` are inclusive indices into `Sequence.messages`.
    `kind` mirrors the standard UML operators ("alt", "opt", "loop"); the
    parsers currently emit "alt" per if-branch (one for the if, one for the
    else if present) and reserve "opt" / "loop" for future extensions.
    `label` is the guard / interaction-operator argument text — e.g. the
    `if` condition for an alt fragment.
    """
    kind: Literal["alt", "opt", "loop"]
    label: str
    start_row: int
    end_row: int
    status: DiffStatus = DiffStatus.UNCHANGED


@dataclass
class Sequence:
    name: str
    lifelines: list[Lifeline] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    fragments: list[Fragment] = field(default_factory=list)
    location: SourceLocation | None = None
    status: DiffStatus = DiffStatus.UNCHANGED

    def stable_id(self) -> str:
        return _stable_id("Sequence", self.name)


@dataclass
class Association:
    """Explicit association between two classes (by qualified name).

    Parsers do not produce these — attribute-typed references already cover the
    code-derived case via `resolve_association`. The editor uses Association to
    let users draw "bare" relationships that don't correspond to any field.
    """
    source: str
    target: str
    name: str | None = None
    source_multiplicity: str | None = None
    target_multiplicity: str | None = None
    source_role: str | None = None
    target_role: str | None = None
    status: DiffStatus = DiffStatus.UNCHANGED


SourceLanguage = Literal[
    "python", "csharp", "typescript", "svelte", "odin", "lua", "julia"
]

# The single source of truth for "which languages does this build support".
# Derived from the type so the runtime check and the type check can never
# disagree; every dispatch site validates against this rather than repeating
# the tuple. Note that support is layered — a language always has a UML parser
# here, but `cdec enforce` and `cdec lock` additionally need a conformance
# analyzer and an AST fingerprinter (TypeScript and Svelte have neither yet, and
# say so when asked).
SUPPORTED_LANGUAGES: tuple[str, ...] = get_args(SourceLanguage)


@dataclass
class Project:
    source_language: SourceLanguage
    packages: list[Package] = field(default_factory=list)
    activities: list[Activity] = field(default_factory=list)
    sequences: list[Sequence] = field(default_factory=list)
    associations: list[Association] = field(default_factory=list)
    root_path: str = ""

    def iter_classes(self) -> Iterator[Class]:
        for pkg in _walk_packages(self.packages):
            yield from pkg.classes


def _walk_packages(packages: list[Package]) -> Iterator[Package]:
    for pkg in packages:
        yield pkg
        yield from _walk_packages(pkg.sub_packages)


def _stable_id(kind: str, qualified_name: str) -> str:
    """Deterministic ID for cross-revision matching.

    sha1 is used purely as a hash (no security implications); the prefix keeps
    IDs readable in the XMI.
    """
    h = sha1(f"{kind}|{qualified_name}".encode("utf-8")).hexdigest()[:16]
    return f"{kind.lower()}-{h}"
