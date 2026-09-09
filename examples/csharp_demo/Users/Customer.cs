using Notifications;

namespace Users;

public class Customer : User
{
    public INotifier Notifier { get; set; }
    public string Address { get; set; } = "";

    public Customer(string email, string name, INotifier notifier)
        : base(email, name)
    {
        Notifier = notifier;
    }

    public override string Role()
    {
        return "customer";
    }

    public bool Charge(decimal amount)
    {
        return amount > 0;
    }
}
