using Ai00.Connector.Service;
using Ai00.Connector.Contracts;
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

    [Fact]
    public void OperationSigningKeyIsProtectedAtRestAndRoundTrips()
    {
        var path = Path.Combine(_directory, "operation.keys");
        var values = new Dictionary<string, string> {
            ["key.device.1"] = new string('s', 64),
        };

        ProtectedSecretStore.Save(path, values);

        Assert.DoesNotContain(new string('s', 64), File.ReadAllText(path));
        Assert.Equal(values["key.device.1"], ProtectedSecretStore.Load(path)["key.device.1"]);
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory)) Directory.Delete(_directory, true);
    }
}
