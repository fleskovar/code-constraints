namespace Notifications;

public interface INotifier
{
    bool Send(string to, string message);
}
