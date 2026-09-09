using System.Collections.Generic;

namespace Catalog;

// Catalog -> Catalog. A self-edge is dropped before the rule sees it.
public class Author
{
    public string Name { get; }
    public List<Book> Books { get; }

    public Author(string name) { Name = name; Books = new List<Book>(); }
}
