using System.Collections.Generic;
using Orders;

namespace Catalog;

// Catalog -> Orders. `List<Order>` is unwrapped to `Order`.
public class Book
{
    public string Title { get; }
    public List<Order> Orders { get; }

    public Book(string title) { Title = title; Orders = new List<Order>(); }
}
