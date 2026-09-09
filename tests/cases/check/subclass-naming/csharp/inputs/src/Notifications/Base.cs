namespace Notifications;

// The base does not inherit from itself, so it is never examined.
public abstract class Notification
{
    public abstract void Send(string message);
}
