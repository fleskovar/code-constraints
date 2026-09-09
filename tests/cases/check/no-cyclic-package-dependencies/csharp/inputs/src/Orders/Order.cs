using Catalog;
using Users;

namespace Orders;

// Orders -> Users (closing the cycle) and Orders -> Catalog (acyclic).
public class Order
{
    public Customer Buyer { get; }
    public Book Item { get; }

    public Order(Customer buyer, Book item) { Buyer = buyer; Item = item; }
}
