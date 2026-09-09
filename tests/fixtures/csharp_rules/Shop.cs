// Fixture exercising every v1 architectural-rule tag (C#).
using System.Collections.Generic;
using CodeConstraints.Rules;

namespace Shop
{
    [Layer("domain")]
    [Sealed]
    public class Repository
    {
        public object Find(int key) => null;
    }

    public class SpecialRepository : Repository { }  // sealed VIOLATION

    [Immutable]
    public class Money
    {
        private int amount;

        public Money(int amount) { this.amount = amount; }

        public int Add(int other) => this.amount + other;  // clean

        public void Reset() { this.amount = 0; }  // immutable VIOLATION
    }

    public class OrderService
    {
        [NoInstantiation(Allow = new[] { "List" })]
        public List<int> Collect()
        {
            var acc = new List<int>();  // allowed by Allow
            return acc;
        }

        [NoInstantiation]
        public int Total(List<int> items) => 0;  // clean
    }

    [Factory(Creates = new[] { "Repository" })]
    public class RepositoryFactory
    {
        public Repository Create() => new Repository();  // allowed: designated factory
    }

    public class Sneaky
    {
        public Repository Make() => new Repository();  // factory VIOLATION
    }
}
