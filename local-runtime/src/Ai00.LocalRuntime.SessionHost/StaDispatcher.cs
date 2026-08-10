using System.Collections.Concurrent;

namespace Ai00.LocalRuntime.SessionHost;

public sealed class StaDispatcher : IDisposable
{
    private readonly BlockingCollection<Action> _queue = new();
    private readonly Thread _thread;
    public StaDispatcher()
    {
        _thread = new Thread(() => { foreach (var action in _queue.GetConsumingEnumerable()) action(); }) { IsBackground = true, Name = "AI00 VisMockup STA" };
        _thread.SetApartmentState(ApartmentState.STA);
        _thread.Start();
    }
    public Task<T> InvokeAsync<T>(Func<T> action)
    {
        var completion = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        _queue.Add(() => { try { completion.SetResult(action()); } catch (Exception ex) { completion.SetException(ex); } });
        return completion.Task;
    }
    public void Dispose() { _queue.CompleteAdding(); _thread.Join(TimeSpan.FromSeconds(5)); _queue.Dispose(); }
}
