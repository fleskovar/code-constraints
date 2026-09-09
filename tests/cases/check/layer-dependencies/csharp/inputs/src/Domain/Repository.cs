using CodeConstraints.Rules;

namespace Domain;

// Same layer as `Order`: same-layer edges are always allowed.
[Layer("domain")]
public interface IOrderRepository
{
    void Save(Order order);
}
