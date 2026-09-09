namespace Notifications;

public class SmsNotifier : INotifier
{
    public string ShortCode { get; set; } = "12345";

    public string MobileProvider;

    public bool Send(string to, string message)
    {
        return message.Length <= 160;
    }
}
