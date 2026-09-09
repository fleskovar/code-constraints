namespace Notifications;

// Not matched by `classes:`, so its churn is invisible to this rule.
public class SmsNotifier : Notification
{
    public override void Send(string message, bool urgent) { }

    public string Preview() { return "sms"; }
}
