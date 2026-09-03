using System.Security.Cryptography;
using System.Text.Json;

namespace Ai00.Connector.Service;

public sealed record DeviceCredential(
    string DeviceId,
    string UserId,
    string WindowsSid,
    string DeviceToken);

public interface IDeviceCredentialStore
{
    string StoragePath { get; }
    void Save(DeviceCredential credential);
    DeviceCredential Load();
}

public sealed class DeviceCredentialStore(string storagePath) : IDeviceCredentialStore
{
    private static readonly byte[] Entropy = "AI00 Connector device credential v1"u8.ToArray();
    public string StoragePath { get; } = Path.GetFullPath(storagePath);

    public void Save(DeviceCredential credential)
    {
        if (string.IsNullOrWhiteSpace(credential.DeviceId) ||
            string.IsNullOrWhiteSpace(credential.UserId) ||
            string.IsNullOrWhiteSpace(credential.WindowsSid) ||
            string.IsNullOrWhiteSpace(credential.DeviceToken))
            throw new InvalidOperationException("device_credential_invalid");
        var clear = JsonSerializer.SerializeToUtf8Bytes(credential);
        var cipher = ProtectedData.Protect(clear, Entropy, DataProtectionScope.LocalMachine);
        var directory = Path.GetDirectoryName(StoragePath)
            ?? throw new InvalidOperationException("device_credential_path_invalid");
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

    public DeviceCredential Load()
    {
        if (!File.Exists(StoragePath)) throw new InvalidOperationException("device_enrollment_required");
        var clear = ProtectedData.Unprotect(File.ReadAllBytes(StoragePath), Entropy, DataProtectionScope.LocalMachine);
        try
        {
            return JsonSerializer.Deserialize<DeviceCredential>(clear)
                ?? throw new InvalidOperationException("device_credential_invalid");
        }
        finally
        {
            CryptographicOperations.ZeroMemory(clear);
        }
    }
}
