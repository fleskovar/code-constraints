using System.Collections.Generic;

namespace Catalog;

public class Author
{
    public string Name { get; }
    public float TestVar { get; }

    public Author(string name) { Name = name; TestVar = 0; }

    // public -> private: an access-level change.
    private List<Book> Books() { return new List<Book>(); }

    // instance -> static: a modifier change.
    public static string Format() { return "x"; }
}
