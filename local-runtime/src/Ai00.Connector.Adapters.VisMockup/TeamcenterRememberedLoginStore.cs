using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Ai00.Connector.Adapters.VisMockup;

// Only the App-owned local test host constructs this store. The credential is
// encrypted for the current Windows user and never enters logs or diagnostics.
public sealed class TeamcenterRememberedLoginStore(string root)
{
    private readonly string path = Path.Combine(root, "teamcenter-login.v1.dpapi");
    private static readonly byte[] Entropy = SHA256.HashData(Encoding.UTF8.GetBytes("AI00 Teamcenter test login v1"));
    private sealed record Saved(string EndpointId, string Username, string Password, DateTimeOffset ExpiresAt);

    public (string EndpointId, string Username, string Password)? Load()
    {
        if (!File.Exists(path)) return null;
        byte[]? clear = null;
        try
        {
            clear = ProtectedData.Unprotect(File.ReadAllBytes(path), Entropy, DataProtectionScope.CurrentUser);
            var value = JsonSerializer.Deserialize<Saved>(clear);
            if (value is not { EndpointId: "tc-production" } || string.IsNullOrWhiteSpace(value.Username)
                || string.IsNullOrEmpty(value.Password) || value.ExpiresAt <= DateTimeOffset.UtcNow)
            { Delete(); return null; }
            return (value.EndpointId, value.Username, value.Password);
        }
        catch (Exception error) when (error is CryptographicException or JsonException or IOException or UnauthorizedAccessException)
        { Delete(); return null; }
        finally { if (clear is not null) CryptographicOperations.ZeroMemory(clear); }
    }

    public void Save(string endpointId, string username, string password)
    {
        var clear = JsonSerializer.SerializeToUtf8Bytes(new Saved(endpointId, username, password,
            DateTimeOffset.UtcNow.AddDays(7)));
        var temporary = path + ".tmp-" + Guid.NewGuid().ToString("N");
        try
        {
            var cipher = ProtectedData.Protect(clear, Entropy, DataProtectionScope.CurrentUser);
            using (var file = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                       4096, FileOptions.WriteThrough)) { file.Write(cipher); file.Flush(true); }
            File.Move(temporary, path, true);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(clear);
            if (File.Exists(temporary)) File.Delete(temporary);
        }
    }

    public void Delete() { if (File.Exists(path)) File.Delete(path); }
}
