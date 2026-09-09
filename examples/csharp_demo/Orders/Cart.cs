using Catalog;
using Users;

namespace Orders;

public class Cart
{
    public Customer Customer { get; set; }
    public List<OrderItem> Items { get; set; } = new();

    public Cart(Customer customer)
    {
        Customer = customer;
    }

    public bool AddItem(Book book, int quantity = 1)
    {
        // <uml-sequence name="cart_add_item" root="this">
        if (book.IsAvailable(quantity))
        {
            var item = new OrderItem(book, quantity);
            Items.Add(item);
            return true;
        }
        return false;
        // </uml-sequence>
    }

    public decimal Total()
    {
        decimal sum = 0;
        foreach (var it in Items)
        {
            sum += it.Subtotal();
        }
        return sum;
    }

    public string Checkout(decimal paymentAmount)
    {
        // <uml-activity name="cart_checkout" granularity="control-flow">
        if (Items.Count == 0)
        {
            return "empty";
        }
        if (paymentAmount < Total())
        {
            return "underpaid";
        }
        foreach (var item in Items)
        {
            item.Book.Reserve(item.Quantity);
        }
        return "ok";
        // </uml-activity>
    }
}
