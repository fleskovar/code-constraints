namespace Notifications;

public abstract class Notification
{
    public abstract void Send(string message);
}

public class SmsNotifier : Notification
{
    public override void Send(string message) { }
}

public class EmailNotifier : Notification
{
    public override void Send(string message) { }
}
