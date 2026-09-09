using CodeConstraints.Rules;

using Domain;

namespace App;

// application -> domain: allowed by the matrix.
[Layer("application")]
public class CheckoutHandler
{
    public Order Order { get; }

    public CheckoutHandler(Order order) { Order = order; }
}
