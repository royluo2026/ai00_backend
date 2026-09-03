using System.Security.Cryptography;
using System.Text.Json;

namespace Ai00.Connector.Contracts;

public sealed record ConnectorIdentityCredential(
    string DeviceId,
    string UserId,
    string WindowsSid,
    string DeviceToken);

public static class ConnectorIdentityStore
{
    private static readonly byte[] Entropy = "AI00 Connector device credential v1"u8.ToArray();

    public static ConnectorIdentityCredential Load(string path)
    {
        if (!File.Exists(path)) throw new InvalidOperationException("connector_pairing_required");
        var clear = ProtectedData.Unprotect(File.ReadAllBytes(path), Entropy, DataProtectionScope.LocalMachine);
        try
        {
            return JsonSerializer.Deserialize<ConnectorIdentityCredential>(clear)
                ?? throw new InvalidOperationException("connector_credential_invalid");
        }
        finally
        {
            CryptographicOperations.ZeroMemory(clear);
        }
    }
}
