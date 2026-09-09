using CodeConstraints.Rules;

using Domain;

namespace Infrastructure;

[Layer("infrastructure")]
public class SqlConnection
{
    public void Execute(string sql) { }
}

// infrastructure -> domain: explicitly allowed. Dependency inversion.
[Layer("infrastructure")]
public class SqlOrderRepository : IOrderRepository
{
    public void Save(Order order) { }
}
