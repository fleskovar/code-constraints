namespace Users;

// In `to:` but never referenced from Catalog.
public class Customer
{
    public string Email { get; }

    public Customer(string email) { Email = email; }
}
