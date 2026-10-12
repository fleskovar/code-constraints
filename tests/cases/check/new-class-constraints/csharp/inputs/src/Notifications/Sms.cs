namespace Notifications;

// New. Extends the approved base directly and is sealed. Passes.
public sealed class SmsNotifier : Notifier
{
    public override void Send(string message) { }
}
