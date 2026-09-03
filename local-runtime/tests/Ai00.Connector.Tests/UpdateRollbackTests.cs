using Ai00.Connector.Service;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class UpdateRollbackTests
{
    [Fact]
    public async Task FailedPostSwitchHealthCheckRollsBackPreviousSlot()
    {
        var slots = new FakeSlots();
        var updater = new UpdateCoordinator(new AcceptingVerifier(), slots);

        var state = await updater.ApplyAsync(
            new UpdatePackage("connector.msi", new("1.1.0", "stable", "https://ai00.invalid/connector.msi", new string('a', 64), "signature")),
            _ => Task.FromResult(false), default);

        Assert.Equal(UpdateState.RolledBack, state);
        Assert.True(slots.RollbackCalled);
    }

    private sealed class AcceptingVerifier : IUpdatePackageVerifier
    {
        public void RequireTrusted(UpdatePackage package) { }
    }

    private sealed class FakeSlots : IUpdateSlots
    {
        public bool RollbackCalled { get; private set; }
        public Task DrainAsync(CancellationToken cancellationToken) => Task.CompletedTask;
        public Task SwitchAsync(UpdatePackage package, CancellationToken cancellationToken) => Task.CompletedTask;
        public Task RollbackAsync(CancellationToken cancellationToken) { RollbackCalled = true; return Task.CompletedTask; }
    }
}
