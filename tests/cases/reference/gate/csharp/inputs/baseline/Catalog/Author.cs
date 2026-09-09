using System.Collections.Generic;

namespace Catalog;

public class Author
{
    public string Name { get; }

    public Author(string name) { Name = name; }

    public List<Book> Books() { return new List<Book>(); }

    public string Format() { return Name; }
}
