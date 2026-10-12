namespace Notifications;

public abstract class Notifier
{
    public abstract void Send(string message);
}

public class EmailNotifier : Notifier
{
    public override void Send(string message) { }
}

// No approved base and not sealed. It is in the baseline, so it is not new.
public class LegacyQueue
{
    public void Push(string message) { }
}
