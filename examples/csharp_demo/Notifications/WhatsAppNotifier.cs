namespace Notifications;

public class WhatsAppNotifier : INotifier
{
    public string Sender { get; set; } = "noreply@bookstore.com";
    public string SmtpHost { get; set; } = "localhost";

    public int phone_number;
    public int country_code;

    public bool Send(string to, string message)
    {
        return to.Contains("@");
    }
}
