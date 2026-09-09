using Catalog;

namespace Orders;

public class OrderItem
{
    public Book Book { get; set; }
    public int Quantity { get; set; }

    public OrderItem(Book book, int quantity)
    {
        Book = book;
        Quantity = quantity;
    }

    public decimal Subtotal()
    {
        return Book.Price * Quantity;
    }
}
