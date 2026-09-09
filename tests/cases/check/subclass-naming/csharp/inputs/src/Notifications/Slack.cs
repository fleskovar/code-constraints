namespace Notifications;

// The violation: inherits the base, name does not match /.*Notifier$/.
public class SlackHook : Notification
{
    public override void Send(string message) { }
}
