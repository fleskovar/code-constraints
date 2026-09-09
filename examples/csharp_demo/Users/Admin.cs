namespace Users;

public class Admin : User
{
    public int Level { get; set; }

    public Admin(string email, string name, int level = 1)
        : base(email, name)
    {
        Level = level;
    }

    public override string Role()
    {
        return "admin";
    }
}
