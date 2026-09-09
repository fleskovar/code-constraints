namespace Catalog;

public class Author
{
    public string Name { get; set; }
    public string Country { get; set; } = "Unknown";

    public Author(string name)
    {
        Name = name;
    }

    public string DisplayName()
    {
        return $"{Name} ({Country})";
    }
}
