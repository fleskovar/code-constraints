namespace Notifications;

public abstract class Notification
{
    // `Send` gained a parameter. `Describe` is untouched. A private field
    // appeared, but `kinds: [operation]` does not cover attributes.
    private int _retries = 3;

    public abstract void Send(string message, bool urgent);

    public virtual string Describe() { return "notification"; }
}
