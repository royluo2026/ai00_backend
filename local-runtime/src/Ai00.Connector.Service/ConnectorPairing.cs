using System.Diagnostics;
using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Service;

public sealed record BrowserPairingRequest(
    [property: JsonPropertyName("installation_id")] string InstallationId,
    [property: JsonPropertyName("verifier_hash")] string VerifierHash,
    [property: JsonPropertyName("device_name")] string DeviceName,
    [property: JsonPropertyName("runtime_version")] string RuntimeVersion,
    [property: JsonPropertyName("windows_sid_hash")] string WindowsSidHash,
    [property: JsonPropertyName("masked_windows_user")] string MaskedWindowsUser,
    [property: JsonPropertyName("ephemeral_public_key")] string EphemeralPublicKey);

public sealed record BrowserPairingCredential(
    [property: JsonPropertyName("connector_id")] string ConnectorId,
    [property: JsonPropertyName("connector_token")] string ConnectorToken,
    [property: JsonPropertyName("bound_user_id")] string UserId,
    [property: JsonPropertyName("team_id")] string? TeamId,
    [property: JsonPropertyName("plan_signing_key_id")] string PlanSigningKeyId,
    [property: JsonPropertyName("plan_signing_secret")] string PlanSigningSecret);

public sealed class BrowserPairingSession : IDisposable
{
    private readonly RSA _privateKey;
    public string Verifier { get; }
    public string PublicKeyPem { get; }
    public BrowserPairingRequest Request { get; }

    private BrowserPairingSession(RSA privateKey, string verifier, BrowserPairingRequest request)
    {
        _privateKey = privateKey;
        Verifier = verifier;
        PublicKeyPem = privateKey.ExportSubjectPublicKeyInfoPem();
        Request = request with { EphemeralPublicKey = PublicKeyPem };
    }

    public static BrowserPairingSession Create(
        string installationId, string deviceName, string runtimeVersion,
        string windowsSidHash, string maskedWindowsUser)
    {
        var key = RSA.Create(2048);
        var verifier = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32));
        var verifierHash = Convert.ToHexString(
            SHA256.HashData(Encoding.UTF8.GetBytes(verifier))).ToLowerInvariant();
        return new BrowserPairingSession(key, verifier, new(
            installationId, verifierHash, deviceName, runtimeVersion,
            windowsSidHash, maskedWindowsUser, "pending"));
    }

    public BrowserPairingCredential Decrypt(string encryptedEnvelope)
    {
        var encoded = Convert.FromBase64String(encryptedEnvelope);
        byte[] clear;
        try
        {
            var envelope = JsonSerializer.Deserialize<HybridEnvelope>(encoded)
                ?? throw new JsonException();
            var key = _privateKey.Decrypt(
                Convert.FromBase64String(envelope.EncryptedKey), RSAEncryptionPadding.OaepSHA256);
            try
            {
                var cipher = Convert.FromBase64String(envelope.Ciphertext);
                clear = new byte[cipher.Length];
                using var aes = new AesGcm(key, 16);
                aes.Decrypt(
                    Convert.FromBase64String(envelope.Nonce), cipher,
                    Convert.FromBase64String(envelope.Tag), clear);
            }
            finally
            {
                CryptographicOperations.ZeroMemory(key);
            }
        }
        catch (JsonException)
        {
            clear = _privateKey.Decrypt(encoded, RSAEncryptionPadding.OaepSHA256);
        }
        try
        {
            return JsonSerializer.Deserialize<BrowserPairingCredential>(clear)
                ?? throw new InvalidOperationException("connector_pairing_envelope_invalid");
        }
        finally
        {
            CryptographicOperations.ZeroMemory(clear);
        }
    }

    private sealed record HybridEnvelope(
        [property: JsonPropertyName("encrypted_key")] string EncryptedKey,
        [property: JsonPropertyName("nonce")] string Nonce,
        [property: JsonPropertyName("ciphertext")] string Ciphertext,
        [property: JsonPropertyName("tag")] string Tag);

    public void Dispose() => _privateKey.Dispose();
}

public static class ConnectorPairing
{
    public static async Task RunAsync(string[] arguments, CancellationToken cancellationToken = default)
    {
        var values = arguments
            .Select((value, index) => (value, index))
            .Where(item => item.value.StartsWith("--", StringComparison.Ordinal) && item.index + 1 < arguments.Length)
            .ToDictionary(item => item.value, item => arguments[item.index + 1], StringComparer.Ordinal);
        if (!values.TryGetValue("--gateway", out var gateway) ||
            !Uri.TryCreate(gateway, UriKind.Absolute, out var gatewayUri) ||
            (gatewayUri.Scheme != Uri.UriSchemeHttps && !gatewayUri.IsLoopback))
            throw new InvalidOperationException("Usage: AI00.Connector.Service.exe pair --gateway https://server");

        var root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AI00", "Connector");
        Directory.CreateDirectory(root);
        var installationPath = Path.Combine(root, "installation.id");
        var installationId = File.Exists(installationPath)
            ? File.ReadAllText(installationPath).Trim()
            : "installation-" + Guid.NewGuid().ToString("N");
        if (!File.Exists(installationPath)) File.WriteAllText(installationPath, installationId);
        var sid = WindowsIdentity.GetCurrent().User?.Value
            ?? throw new InvalidOperationException("windows_sid_unavailable");
        var sidHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(sid))).ToLowerInvariant();
        var user = Environment.UserName;
        var maskedUser = user.Length <= 2 ? "**" : $"{user[0]}***{user[^1]}";
        using var pairing = BrowserPairingSession.Create(
            installationId, Environment.MachineName, "1.0.0", sidHash, maskedUser);
        using var http = new HttpClient { BaseAddress = new Uri(gateway.TrimEnd('/') + "/") };
        using var response = await http.PostAsJsonAsync(
            "api/v1/simulation/connectors/pairings", pairing.Request, cancellationToken);
        response.EnsureSuccessStatusCode();
        var created = await response.Content.ReadFromJsonAsync<ApiEnvelope<PairingCreated>>(
            cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("connector_pairing_response_invalid");

        var verificationBase = new Uri(gatewayUri, created.Data.VerificationUri.TrimStart('/'));
        var verificationUri = new UriBuilder(verificationBase) {
            Query = "code=" + Uri.EscapeDataString(created.Data.UserCode),
        }.Uri;
        Console.WriteLine($"Open {verificationUri} and confirm code {created.Data.UserCode}");
        Process.Start(new ProcessStartInfo(verificationUri.ToString()) { UseShellExecute = true });
        BrowserPairingCompletion? completion = null;
        while (DateTimeOffset.UtcNow < created.Data.ExpiresAt && !cancellationToken.IsCancellationRequested)
        {
            using var complete = await http.PostAsJsonAsync(
                $"api/v1/simulation/connectors/pairings/{created.Data.PairingId}/complete",
                new { installation_id = installationId, verifier = pairing.Verifier }, cancellationToken);
            if (complete.IsSuccessStatusCode)
            {
                completion = (await complete.Content.ReadFromJsonAsync<ApiEnvelope<BrowserPairingCompletion>>(
                    cancellationToken: cancellationToken))?.Data;
                break;
            }
            if (complete.StatusCode is not HttpStatusCode.Conflict)
                complete.EnsureSuccessStatusCode();
            await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);
        }
        if (completion is null) throw new InvalidOperationException("connector_pairing_expired");
        var credential = pairing.Decrypt(completion.EncryptedCredentialEnvelope);
        var credentialPath = Path.Combine(root, "device.credential");
        new DeviceCredentialStore(credentialPath).Save(new(
            credential.ConnectorId, credential.UserId, sid, credential.ConnectorToken));
        ProtectedSecretStore.Save(
            Path.Combine(root, "operation.keys"),
            new Dictionary<string, string> { [credential.PlanSigningKeyId] = credential.PlanSigningSecret });
        Environment.SetEnvironmentVariable("Connector__GatewayUrl", gateway.TrimEnd('/'), EnvironmentVariableTarget.Machine);
        Console.WriteLine("AI00 Connector pairing completed. Sign out and sign in once to start SessionHost.");
    }

    private sealed record ApiEnvelope<T>(bool Success, T Data);
    private sealed record PairingCreated(
        [property: JsonPropertyName("pairing_id")] string PairingId,
        [property: JsonPropertyName("user_code")] string UserCode,
        [property: JsonPropertyName("verification_uri")] string VerificationUri,
        [property: JsonPropertyName("expires_at")] DateTimeOffset ExpiresAt);
    private sealed record BrowserPairingCompletion(
        [property: JsonPropertyName("connector_id")] string ConnectorId,
        [property: JsonPropertyName("encrypted_credential_envelope")] string EncryptedCredentialEnvelope,
        [property: JsonPropertyName("envelope_hash")] string EnvelopeHash);
}
