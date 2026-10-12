namespace Testing;

// New, with no base and no `sealed`, but `Testing.**` is in `ignore:`.
public class FakeNotifier
{
    public void Send(string message) { }
}
