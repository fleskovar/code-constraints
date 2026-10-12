namespace Notifications;

// New and sealed, but it extends nothing. One violation.
public sealed class RetryPolicy
{
    public int Attempts { get; set; }
}
