namespace Notifications;

public abstract class Notification
{
    public abstract void Send(string message);
}

// `SmsNotifier` under a new name: the old qualified name is gone.
public class TwilioNotifier : Notification
{
    public override void Send(string message) { }
}

// Same class, rewritten internals. Not a removal.
public class EmailNotifier : Notification
{
    public override void Send(string message) { Publish(message); }

    private void Publish(string message) { }
}
