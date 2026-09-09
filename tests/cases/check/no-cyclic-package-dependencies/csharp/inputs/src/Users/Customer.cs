using Orders;

namespace Users;

// Users -> Orders.
public class Customer
{
    public Order Latest { get; }

    public Customer(Order latest) { Latest = latest; }
}
