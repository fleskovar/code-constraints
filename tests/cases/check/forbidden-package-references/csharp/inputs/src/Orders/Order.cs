using Catalog;

namespace Orders;

// Orders -> Catalog: the permitted direction.
public class Order
{
    public Book Item { get; }

    public Order(Book item) { Item = item; }
}
