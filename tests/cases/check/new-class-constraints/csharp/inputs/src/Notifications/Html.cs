namespace Notifications;

// New. Reaches Notifier through EmailNotifier and is sealed. Passes.
public sealed class HtmlEmailNotifier : EmailNotifier
{
    public override void Send(string message) { }
}
