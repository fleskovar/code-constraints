namespace Notifications;

public abstract class Notification
{
    // A method was added. A CHANGED class is not an ADDED class.
    public abstract void Send(string message);

    public virtual void Retry(int attempts) { }
}

public class SmsNotifier : Notification
{
    public override void Send(string message) { }
}
