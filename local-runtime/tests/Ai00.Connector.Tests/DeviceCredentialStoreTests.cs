using Ai00.Connector.Service;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class DeviceCredentialStoreTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), "ai00-connector-tests", Guid.NewGuid().ToString("N"));

    [Fact]
    public void StoredCredentialDoesNotContainPlaintextTokenAndRoundTripsIdentity()
    {
        var path = Path.Combine(_directory, "device.credential");
        var store = new DeviceCredentialStore(path);
        var credential = new DeviceCredential("device-1", "user-1", "S-1-5-21-test", "secret-token");

        store.Save(credential);

        Assert.DoesNotContain("secret-token", File.ReadAllText(store.StoragePath));
        Assert.Equal(credential, store.Load());
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory)) Directory.Delete(_directory, true);
    }
}
