namespace Notifications;

public abstract class Notification
{
    public abstract void Send(string message);

    public virtual string Describe() { return "notification"; }
}
