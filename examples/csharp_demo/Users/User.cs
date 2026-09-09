namespace Users;

public abstract class User
{
    public string Email { get; set; }
    public string Name { get; set; }

    protected User(string email, string name)
    {
        Email = email;
        Name = name;
    }

    public abstract string Role();
}
