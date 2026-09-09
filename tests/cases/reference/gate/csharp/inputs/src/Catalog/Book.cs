namespace Catalog;

// `class` -> `abstract`. `frozen-members` is structurally blind to this.
public abstract class Book
{
    public string Title { get; }

    public Book(string title) { Title = title; }
}
