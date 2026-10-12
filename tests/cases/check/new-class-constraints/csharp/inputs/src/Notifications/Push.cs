namespace Notifications;

// New. The base is approved, but `sealed` is missing. One violation.
public class PushNotifier : Notifier
{
    public override void Send(string message) { }
}
