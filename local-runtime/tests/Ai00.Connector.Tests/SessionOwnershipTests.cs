using Ai00.Connector.Contracts;
using Ai00.Connector.Service;
using Ai00.Connector.SessionHost;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class SessionOwnershipTests
{
    [Fact]
    public void SecondSessionHostForDeviceAndSidIsRejected()
    {
        using var first = SingleInstanceGuard.Acquire("device-1", "S-1-5-21-test");
        var error = Assert.Throws<ConnectorException>(() =>
            SingleInstanceGuard.Acquire("device-1", "S-1-5-21-test"));
        Assert.Equal("interactive_session_conflict", error.Code);
    }

    [Fact]
    public async Task SupervisorRejectsLoggedOutAndConflictingBoundSessions()
    {
        var binding = new DeviceBinding("device-1", "user-1", "S-1-5-21-test");
        var missing = new SessionHostSupervisor(new StubSessions([]), new StubLauncher());
        Assert.Equal(SessionHostState.Missing, (await missing.EnsureBoundSessionAsync(binding, default)).State);

        var conflict = new SessionHostSupervisor(new StubSessions([1, 2]), new StubLauncher());
        Assert.Equal(SessionHostState.Conflict, (await conflict.EnsureBoundSessionAsync(binding, default)).State);
    }

    private sealed class StubSessions(IReadOnlyList<int> ids) : IWindowsSessionLocator
    {
        public IReadOnlyList<int> ForSid(string windowsSid) => ids;
    }

    private sealed class StubLauncher : ISessionHostLauncher
    {
        public Task EnsureSessionHostAsync(int sessionId, DeviceBinding binding, CancellationToken cancellationToken) => Task.CompletedTask;
    }
}
