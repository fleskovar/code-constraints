namespace Catalog;

public class Book
{
    public string Title { get; set; }
    public Author Author { get; set; }
    public decimal Price { get; set; }
    public int Stock { get; set; }

    public Book(string title, Author author, decimal price, int stock = 0)
    {
        Title = title;
        Author = author;
        Price = price;
        Stock = stock;
    }

    public bool IsAvailable(int requested = 1)
    {
        // <uml-activity name="book_availability" granularity="statement">
        bool inStock = Stock >= requested;
        bool priced = Price > 0;
        bool result = inStock && priced;
        return result;
        // </uml-activity>
    }

    public void Reserve(int quantity)
    {
        Stock -= quantity;
    }
}
