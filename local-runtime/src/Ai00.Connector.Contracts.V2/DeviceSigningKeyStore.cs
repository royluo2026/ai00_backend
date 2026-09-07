using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;

namespace Ai00.Connector.Contracts.V2;

/// <summary>Owns a device key handle. Only its public JWK and signing operations leave this boundary.</summary>
public sealed class DeviceSigningKey : IDisposable
{
    private readonly ECDsa key;
    private bool disposed;
    internal DeviceSigningKey(ECDsa key) => this.key = key;
    public JsonElement PublicJwk
    {
        get { ObjectDisposedException.ThrowIf(disposed, this); return ProtocolV2Signatures.PublicJwk(key); }
    }
    internal string Sign(byte[] data)
    {
        ObjectDisposedException.ThrowIf(disposed, this);
        return ProtocolV2Signatures.Sign(data, key);
    }
    public void Dispose() { if (!disposed) { key.Dispose(); disposed = true; } }
}

/// <summary>Windows x64, current-user DPAPI storage in an explicitly supplied App-owned user-data directory.</summary>
public sealed class DeviceSigningKeyStore
{
    private static readonly byte[] Header = "AI00KEY\x01"u8.ToArray();
    private readonly string directory;
    private readonly byte[] entropy;
    public string StoragePath { get; }

    public DeviceSigningKeyStore(string userDataDirectory)
    {
        if (string.IsNullOrWhiteSpace(userDataDirectory) || !Path.IsPathFullyQualified(userDataDirectory))
            throw new ArgumentException("absolute_app_user_data_directory_required", nameof(userDataDirectory));
        var userData = Path.TrimEndingDirectorySeparator(Path.GetFullPath(userDataDirectory));
        if (userData.StartsWith("\\\\", StringComparison.Ordinal) || userData.Length <= 3 || userData.AsSpan(2).Contains(':'))
            throw new ArgumentException("local_app_user_data_directory_required", nameof(userDataDirectory));
        directory = Path.Combine(userData, "connector-keys");
        StoragePath = Path.Combine(directory, "device-signing-key.v1.dpapi");
        entropy = SHA256.HashData(Encoding.UTF8.GetBytes("AI00 Connector device signing key v1\n" + userData.ToUpperInvariant()));
    }

    public DeviceSigningKey GetOrCreate()
    {
        if (!OperatingSystem.IsWindows() || RuntimeInformation.ProcessArchitecture != Architecture.X64)
            throw new PlatformNotSupportedException("windows_x64_required");
        using var identity = WindowsIdentity.GetCurrent();
        var sid = identity.User ?? throw new CryptographicException("windows_user_required");
        // Serialize creation across host processes. An abandoned mutex indicates a
        // crashed writer; atomic rename means the final file is complete or absent.
        var lockId = CanonicalJsonV2.HexHash(Encoding.UTF8.GetBytes(sid.Value + StoragePath.ToUpperInvariant()));
        using var mutex = new Mutex(false, "Local\\AI00.DeviceSigningKey." + lockId);
        var acquired = false;
        try
        {
            try { acquired = mutex.WaitOne(TimeSpan.FromSeconds(30)); }
            catch (AbandonedMutexException) { acquired = true; }
            if (!acquired) throw new IOException("device_key_store_busy");
            RejectReparseAncestors(directory);
            var security = new DirectorySecurity();
            security.SetAccessRuleProtection(true, false);
            security.SetOwner(sid);
            security.AddAccessRule(new FileSystemAccessRule(sid, FileSystemRights.FullControl,
                InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit, PropagationFlags.None, AccessControlType.Allow));
            var folder = new DirectoryInfo(directory);
            if (!folder.Exists) folder.Create(security);
            else folder.SetAccessControl(security);
            RejectReparseAncestors(StoragePath);
            if (Directory.Exists(StoragePath)) throw new IOException("device_key_file_required");
            if (File.Exists(StoragePath)) return Load(sid);

            using var generated = ECDsa.Create(ECCurve.NamedCurves.nistP256);
            var clear = generated.ExportPkcs8PrivateKey();
            var temporary = StoragePath + ".tmp-" + Guid.NewGuid().ToString("N");
            try
            {
                var cipher = ProtectedData.Protect(clear, entropy, DataProtectionScope.CurrentUser);
                using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                    4096, FileOptions.WriteThrough))
                {
                    stream.Write(Header);
                    stream.Write(cipher);
                    stream.Flush(true);
                }
                File.Move(temporary, StoragePath); // Never overwrite an existing signing identity.
            }
            finally
            {
                CryptographicOperations.ZeroMemory(clear);
                if (File.Exists(temporary)) File.Delete(temporary);
            }
            return Load(sid);
        }
        finally { if (acquired) mutex.ReleaseMutex(); }
    }

    private DeviceSigningKey Load(SecurityIdentifier sid)
    {
        var file = new FileInfo(StoragePath);
        if (file.Length < Header.Length + 1 || file.Length > 16384)
            throw new CryptographicException("device_key_blob_invalid");
        var security = new FileSecurity();
        security.SetAccessRuleProtection(true, false);
        security.SetOwner(sid);
        security.AddAccessRule(new FileSystemAccessRule(sid, FileSystemRights.FullControl, AccessControlType.Allow));
        file.SetAccessControl(security);
        var blob = File.ReadAllBytes(StoragePath);
        if (!blob.AsSpan().StartsWith(Header)) throw new CryptographicException("device_key_blob_version_invalid");
        var clear = ProtectedData.Unprotect(blob[Header.Length..], entropy, DataProtectionScope.CurrentUser);
        var key = ECDsa.Create();
        try
        {
            key.ImportPkcs8PrivateKey(clear, out var consumed);
            if (consumed != clear.Length || key.ExportParameters(false).Curve.Oid.Value != "1.2.840.10045.3.1.7")
                throw new CryptographicException("device_key_blob_invalid");
            return new DeviceSigningKey(key);
        }
        catch { key.Dispose(); throw; }
        finally { CryptographicOperations.ZeroMemory(clear); }
    }

    private static void RejectReparseAncestors(string path)
    {
        for (var current = path; current != null; current = Path.GetDirectoryName(current))
        {
            try
            {
                if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("device_key_reparse_path_forbidden");
            }
            catch (FileNotFoundException) { }
            catch (DirectoryNotFoundException) { }
        }
    }
}

/// <summary>Activation-scoped RSA-OAEP-SHA256 key. Dispose immediately after activation;
/// caller must zero decrypted credential bytes after persisting them with CurrentUser DPAPI.</summary>
public sealed class BootstrapEncryptionKey : IDisposable
{
    private readonly RSA key = RSA.Create(3072);
    private bool disposed;
    public JsonElement PublicJwk
    {
        get
        {
            ObjectDisposedException.ThrowIf(disposed, this);
            var parameters = key.ExportParameters(false);
            return JsonSerializer.SerializeToElement(new { kty = "RSA", n = ProtocolV2Signatures.Encode(parameters.Modulus!),
                e = ProtocolV2Signatures.Encode(parameters.Exponent!) });
        }
    }
    public byte[] Decrypt(byte[] ciphertext)
    {
        ObjectDisposedException.ThrowIf(disposed, this);
        return key.Decrypt(ciphertext, RSAEncryptionPadding.OaepSHA256);
    }
    // Private material stays in the native cryptographic handle; disposal releases
    // that handle without ever materializing/exporting RSA private parameter arrays.
    public void Dispose() { if (!disposed) { key.Dispose(); disposed = true; } }
}
