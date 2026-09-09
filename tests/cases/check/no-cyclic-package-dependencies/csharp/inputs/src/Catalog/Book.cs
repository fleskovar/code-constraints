namespace Catalog;

// A leaf. It cannot be in a cycle, so it never appears in the output.
public class Book
{
    public string Title { get; }

    public Book(string title) { Title = title; }
}
