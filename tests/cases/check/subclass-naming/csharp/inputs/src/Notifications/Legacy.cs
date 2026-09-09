namespace Notifications;

// Also breaks the pattern, but is named in `ignore:`.
public class LegacyPager : Notification
{
    public override void Send(string message) { }
}
