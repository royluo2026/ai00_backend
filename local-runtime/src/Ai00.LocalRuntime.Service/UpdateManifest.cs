using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Ai00.LocalRuntime.Service;

public enum UpdateState { Idle, Downloading, Verifying, Draining, Switching, HealthChecking, Completed, RolledBack }
public sealed record UpdateManifest(string Version, string Channel, string Url, string Sha256, string Signature);

public static class UpdateManifestVerifier
{
    public static bool Verify(UpdateManifest manifest, string publicKeyPem)
    {
        var canonical = JsonSerializer.Serialize(new { manifest.Version, manifest.Channel, manifest.Url, manifest.Sha256 });
        using var rsa = RSA.Create();
        rsa.ImportFromPem(publicKeyPem);
        return rsa.VerifyData(Encoding.UTF8.GetBytes(canonical), Convert.FromBase64String(manifest.Signature), HashAlgorithmName.SHA256, RSASignaturePadding.Pss);
    }

    public static bool VerifyFile(string path, string expectedSha256)
    {
        using var stream = File.OpenRead(path);
        return string.Equals(Convert.ToHexString(SHA256.HashData(stream)), expectedSha256, StringComparison.OrdinalIgnoreCase);
    }
}
