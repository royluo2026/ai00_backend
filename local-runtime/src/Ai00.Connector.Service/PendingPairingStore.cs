using System.Security.Cryptography;
using System.Text.Json;

namespace Ai00.Connector.Service;

public sealed record PendingPairing(
    string BootstrapId,
    string PairingId,
    string InstallationId,
    string Verifier,
    string PrivateKeyPkcs8,
    string GatewayUrl,
    DateTimeOffset ExpiresAt);

public sealed class PendingPairingStore(string storagePath)
{
    private static readonly byte[] Entropy = "AI00 Connector pending pairing v1"u8.ToArray();
    public string StoragePath { get; } = Path.GetFullPath(storagePath);

    public void Save(PendingPairing pending)
    {
        var clear = JsonSerializer.SerializeToUtf8Bytes(pending);
        var cipher = ProtectedData.Protect(clear, Entropy, DataProtectionScope.LocalMachine);
        var directory = Path.GetDirectoryName(StoragePath)
            ?? throw new InvalidOperationException("pending_pairing_path_invalid");
        Directory.CreateDirectory(directory);
        var temporaryPath = StoragePath + ".tmp-" + Guid.NewGuid().ToString("N");
        try
        {
            File.WriteAllBytes(temporaryPath, cipher);
            File.Move(temporaryPath, StoragePath, true);
        }
        finally
        {
            if (File.Exists(temporaryPath)) File.Delete(temporaryPath);
            CryptographicOperations.ZeroMemory(clear);
        }
    }

    public PendingPairing? Load()
    {
        if (!File.Exists(StoragePath)) return null;
        var clear = ProtectedData.Unprotect(
            File.ReadAllBytes(StoragePath), Entropy, DataProtectionScope.LocalMachine);
        try
        {
            return JsonSerializer.Deserialize<PendingPairing>(clear)
                ?? throw new InvalidOperationException("pending_pairing_invalid");
        }
        finally
        {
            CryptographicOperations.ZeroMemory(clear);
        }
    }

    public void Delete() => File.Delete(StoragePath);
}
