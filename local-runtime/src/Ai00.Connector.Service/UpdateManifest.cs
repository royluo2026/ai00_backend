using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Ai00.Connector.Service;

public enum UpdateState { Idle, Downloading, Verifying, Draining, Switching, HealthChecking, Completed, RolledBack }
public sealed record UpdateManifest(string Version, string Channel, string Url, string Sha256, string Signature);
public sealed record UpdatePackage(string Path, UpdateManifest Manifest);

public interface IUpdatePackageVerifier
{
    void RequireTrusted(UpdatePackage package);
}

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

public sealed class TrustedUpdatePackageVerifier(
    string organizationManifestPublicKeyPem,
    IReadOnlySet<string> organizationSignerThumbprints) : IUpdatePackageVerifier
{
    public void RequireTrusted(UpdatePackage package)
    {
        if (!Uri.TryCreate(package.Manifest.Url, UriKind.Absolute, out var source) || source.Scheme != Uri.UriSchemeHttps)
            throw new InvalidOperationException("update_transport_invalid");
        if (!UpdateManifestVerifier.Verify(package.Manifest, organizationManifestPublicKeyPem))
            throw new InvalidOperationException("update_manifest_signature_invalid");
        if (!UpdateManifestVerifier.VerifyFile(package.Path, package.Manifest.Sha256))
            throw new InvalidOperationException("update_package_hash_invalid");
        try
        {
            using var certificate = new System.Security.Cryptography.X509Certificates.X509Certificate2(
                System.Security.Cryptography.X509Certificates.X509Certificate.CreateFromSignedFile(package.Path));
            using var chain = new System.Security.Cryptography.X509Certificates.X509Chain();
            if (!chain.Build(certificate) || !organizationSignerThumbprints.Contains(certificate.Thumbprint))
                throw new InvalidOperationException("update_authenticode_invalid");
        }
        catch (System.Security.Cryptography.CryptographicException)
        {
            throw new InvalidOperationException("update_authenticode_invalid");
        }
    }
}
