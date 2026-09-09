namespace Support;

// [Sealed] deleted here too - but `Support.**` is outside `classes:`.
public class AuditEntry
{
    public string Action { get; }

    public AuditEntry(string action) { Action = action; }
}
