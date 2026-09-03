using System.Security.Cryptography;
using System.Text.Json;

namespace Ai00.Connector.Contracts;

public static class ProtectedSecretStore
{
    private static readonly byte[] Entropy = "AI00 Connector operation keys v1"u8.ToArray();

    public static void Save(string path, IReadOnlyDictionary<string, string> values)
    {
        if (values.Count == 0 || values.Any(item => item.Key.Length == 0 || item.Value.Length < 32))
            throw new InvalidOperationException("operation_signing_keys_invalid");
        var clear = JsonSerializer.SerializeToUtf8Bytes(values);
        try
        {
            var cipher = ProtectedData.Protect(clear, Entropy, DataProtectionScope.LocalMachine);
            Directory.CreateDirectory(Path.GetDirectoryName(path)
                ?? throw new InvalidOperationException("secret_store_path_invalid"));
            File.WriteAllBytes(path, cipher);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(clear);
        }
    }

    public static IReadOnlyDictionary<string, string> Load(string path)
    {
        var clear = ProtectedData.Unprotect(File.ReadAllBytes(path), Entropy, DataProtectionScope.LocalMachine);
        try
        {
            return JsonSerializer.Deserialize<Dictionary<string, string>>(clear)
                ?? throw new InvalidOperationException("operation_signing_keys_invalid");
        }
        finally
        {
            CryptographicOperations.ZeroMemory(clear);
        }
    }
}
