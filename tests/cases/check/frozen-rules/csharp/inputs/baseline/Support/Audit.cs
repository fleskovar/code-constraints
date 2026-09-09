using CodeConstraints.Rules;

namespace Support;

[Sealed]
public class AuditEntry
{
    public string Action { get; }

    public AuditEntry(string action) { Action = action; }
}
