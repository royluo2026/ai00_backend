using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text.Json.Nodes;
using Ai00.Connector.Contracts.V2;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class DeviceSigningKeyStoreTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "ai00-v2-keys-" + Guid.NewGuid().ToString("N"));

    [Fact]
    public void CurrentUserDpapiRoundtripRetainsSigningIdentityAndRestrictsAcl()
    {
        var store = new DeviceSigningKeyStore(Path.Combine(root, "app"));
        using var first = store.GetOrCreate();
        using var second = store.GetOrCreate();
        Assert.Equal(first.PublicJwk.GetRawText(), second.PublicJwk.GetRawText());
        var outcome = ProtocolV2VectorTests.Vector["outcome"]!.DeepClone().AsObject();
        outcome.Remove("signature");
        var signed = OutcomeV2Signer.Sign(outcome.ToJsonString(), second);
        OutcomeV2.ParseAndVerify(signed, first.PublicJwk.GetRawText());
        var rules = new FileInfo(store.StoragePath).GetAccessControl().GetAccessRules(true, true, typeof(SecurityIdentifier));
        var sid = WindowsIdentity.GetCurrent().User!;
        Assert.All(rules.Cast<FileSystemAccessRule>(), rule => Assert.Equal(sid, rule.IdentityReference));
        Assert.Single(Directory.GetFiles(Path.GetDirectoryName(store.StoragePath)!));
    }

    [Theory]
    [InlineData("corrupt")]
    [InlineData("version")]
    [InlineData("truncated")]
    public void CorruptOrUnknownVersionBlobIsNeverReplaced(string mode)
    {
        var store = new DeviceSigningKeyStore(Path.Combine(root, "app"));
        using (store.GetOrCreate()) { }
        var blob = File.ReadAllBytes(store.StoragePath);
        if (mode == "version") blob[0] ^= 0xff;
        else if (mode == "corrupt") blob[^1] ^= 0xff;
        else blob = blob[..5];
        File.WriteAllBytes(store.StoragePath, blob);
        Assert.ThrowsAny<CryptographicException>(() => store.GetOrCreate());
        Assert.Equal(blob, File.ReadAllBytes(store.StoragePath));
    }

    [Fact]
    public void CopyingProtectedKeyIntoAnotherUserDataDirectoryFailsClosed()
    {
        var original = new DeviceSigningKeyStore(Path.Combine(root, "first"));
        var other = new DeviceSigningKeyStore(Path.Combine(root, "second"));
        using (original.GetOrCreate()) { }
        Directory.CreateDirectory(Path.GetDirectoryName(other.StoragePath)!);
        File.Copy(original.StoragePath, other.StoragePath);
        Assert.ThrowsAny<CryptographicException>(() => other.GetOrCreate());
    }

    [Fact]
    public async Task ConcurrentCreationReturnsOneIdentityAndOrphanTemporaryFileIsHarmless()
    {
        var store = new DeviceSigningKeyStore(Path.Combine(root, "app"));
        Directory.CreateDirectory(Path.GetDirectoryName(store.StoragePath)!);
        File.WriteAllText(store.StoragePath + ".tmp-interrupted", "incomplete protected write");
        var results = await Task.WhenAll(Enumerable.Range(0, 8).Select(_ => Task.Run(() =>
        {
            using var key = store.GetOrCreate();
            return key.PublicJwk.GetRawText();
        })));
        Assert.Single(results.Distinct());
    }

    [Fact]
    public void RequiresExplicitAbsoluteDirectoryAndRejectsDirectoryAtKeyPath()
    {
        Assert.Throws<ArgumentException>(() => new DeviceSigningKeyStore("relative"));
        var store = new DeviceSigningKeyStore(Path.Combine(root, "app"));
        Directory.CreateDirectory(store.StoragePath);
        Assert.ThrowsAny<IOException>(() => store.GetOrCreate());
    }

    [Fact]
    public void BootstrapRsaIsMemoryOnlyAndDisposedAfterActivation()
    {
        var bootstrap = new BootstrapEncryptionKey();
        using var encryptor = RSA.Create();
        var jwk = bootstrap.PublicJwk;
        encryptor.ImportParameters(new RSAParameters { Modulus = ProtocolV2VectorTests.Decode(jwk.GetProperty("n").GetString()!),
            Exponent = ProtocolV2VectorTests.Decode(jwk.GetProperty("e").GetString()!) });
        var cipher = encryptor.Encrypt("credential"u8.ToArray(), RSAEncryptionPadding.OaepSHA256);
        var clear = bootstrap.Decrypt(cipher);
        Assert.Equal("credential"u8.ToArray(), clear);
        CryptographicOperations.ZeroMemory(clear);
        bootstrap.Dispose();
        Assert.Throws<ObjectDisposedException>(() => bootstrap.Decrypt(cipher));
        Assert.False(Directory.Exists(root));
    }

    public void Dispose()
    {
        if (Directory.Exists(root)) Directory.Delete(root, true);
    }
}
