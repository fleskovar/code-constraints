using Users;

namespace Catalog;

// The violation: a `Users.Customer` parameter type.
public class Book
{
    public string Title { get; }
    public Customer ReservedBy { get; }

    public Book(string title, Customer reservedBy)
    {
        Title = title;
        ReservedBy = reservedBy;
    }
}
