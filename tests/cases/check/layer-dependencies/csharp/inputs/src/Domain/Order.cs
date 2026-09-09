using CodeConstraints.Rules;

using Infrastructure;
using Support;

namespace Domain;

// The violation: `domain` allows nothing, SqlConnection is `infrastructure`.
// The `Logger` reference is invisible - Logger carries no [Layer] tag.
[Layer("domain")]
public class Order
{
    public SqlConnection Conn { get; }
    public Logger Log { get; }

    public Order(SqlConnection conn, Logger log) { Conn = conn; Log = log; }
}
