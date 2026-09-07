using Ai00.Connector.Contracts;
using Ai00.Connector.Service;
using Ai00.Connector.SessionHost;
using Ai00.Connector.Tray;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class SessionOwnershipTests
{
    [Fact]
    public void TrayRejectsMalformedOrRemoteHttpPairingUrisBeforePipeAccess()
    {
        Assert.False(PairingPipeClient.IsAllowed(new Uri("https://example.com/pair")));
        Assert.False(PairingPipeClient.IsAllowed(new Uri(
            "ai00connector://pair?gateway=http%3A%2F%2Fexample.com&bootstrap_id=b&bootstrap_token=t")));
        Assert.True(PairingPipeClient.IsAllowed(new Uri(
            "ai00connector://pair?gateway=https%3A%2F%2Fai00.example&bootstrap_id=b&bootstrap_token=t")));
    }

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

    [Fact]
    public void TrayStartsSessionHostOnlyWhenCurrentSessionHasNone()
    {
        var starts = 0;

        Assert.True(SessionHostProcess.EnsureStarted(() => false, () => starts++));
        Assert.False(SessionHostProcess.EnsureStarted(() => true, () => starts++));
        Assert.Equal(1, starts);
    }

    [Fact]
    public void BrokerAcceptsOnlyCompleteIdentityForItsInteractiveSid()
    {
        const string sid = "S-1-5-21-test";
        Assert.True(SessionHostBroker.IsAllowed(
            new SessionHostStartRequest("device-1", "user-1", sid), sid));
        Assert.False(SessionHostBroker.IsAllowed(
            new SessionHostStartRequest("device-1", "user-1", "S-1-5-21-other"), sid));
        Assert.False(SessionHostBroker.IsAllowed(
            new SessionHostStartRequest("", "user-1", sid), sid));
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
