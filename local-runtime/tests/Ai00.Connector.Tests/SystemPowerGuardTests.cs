using Ai00.Connector.Service;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class SystemPowerGuardTests
{
    [Fact]
    public void PowerRequestIsReleasedWhenPlanThrows()
    {
        var native = new RecordingPowerNative();
        var power = new SystemPowerGuard(native);

        Assert.Throws<InvalidOperationException>(ThrowAfterAcquire);

        void ThrowAfterAcquire()
        {
            using var guard = power.Acquire("plan-1");
            throw new InvalidOperationException("boom");
        }

        Assert.Equal(1, native.ClearCalls);
        Assert.Equal(1, native.CloseCalls);
        Assert.Equal([PowerRequestType.SystemRequired], native.SetTypes);
    }

    private sealed class RecordingPowerNative : IPowerRequestNative
    {
        public int ClearCalls { get; private set; }
        public int CloseCalls { get; private set; }
        public List<PowerRequestType> SetTypes { get; } = [];
        public nint Create(string reason) => 42;
        public bool Set(nint handle, PowerRequestType type) { SetTypes.Add(type); return true; }
        public bool Clear(nint handle, PowerRequestType type) { ClearCalls++; return true; }
        public void Close(nint handle) => CloseCalls++;
    }
}
