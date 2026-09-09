using Users;

namespace Orders;

// References the forbidden target, but is not in `from:`. The rule is
// directional.
public class Order
{
    public Customer Buyer { get; }

    public Order(Customer buyer) { Buyer = buyer; }
}
