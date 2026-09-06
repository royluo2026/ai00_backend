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
    [property: JsonPropertyName("bootstrap_token")] string BootstrapToken,
    [property: JsonPropertyName("installation_id")] string InstallationId,
    [property: JsonPropertyName("verifier_hash")] string VerifierHash,
    [property: JsonPropertyName("device_name")] string DeviceName,
    [property: JsonPropertyName("runtime_version")] string RuntimeVersion,
    [property: JsonPropertyName("windows_sid_hash")] string WindowsSidHash,
    [property: JsonPropertyName("masked_windows_user")] string MaskedWindowsUser,
    [property: JsonPropertyName("ephemeral_public_key")] string EphemeralPublicKey);

public sealed record BrowserPairingCredential(
    [property: JsonPropertyName("connector_id")] string ConnectorId,
    [property: JsonPropertyName("installation_id")] string InstallationId,
    [property: JsonPropertyName("connector_token")] string ConnectorToken,
    [property: JsonPropertyName("bound_user_id")] string UserId,
    [property: JsonPropertyName("team_id")] string? TeamId,
    [property: JsonPropertyName("activation_proof")] string ActivationProof,
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
        string windowsSidHash, string maskedWindowsUser, string bootstrapToken = "")
    {
        var key = RSA.Create(2048);
        var verifier = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32));
        var verifierHash = Convert.ToHexString(
            SHA256.HashData(Encoding.UTF8.GetBytes(verifier))).ToLowerInvariant();
        return new BrowserPairingSession(key, verifier, new(
            bootstrapToken, installationId, verifierHash, deviceName, runtimeVersion,
            windowsSidHash, maskedWindowsUser, "pending"));
    }

    public static BrowserPairingSession Restore(
        BrowserPairingRequest request, string verifier, string privateKeyPkcs8)
    {
        var key = RSA.Create();
        key.ImportPkcs8PrivateKey(Convert.FromBase64String(privateKeyPkcs8), out _);
        return new BrowserPairingSession(key, verifier, request);
    }

    public string ExportPrivateKey() =>
        Convert.ToBase64String(_privateKey.ExportPkcs8PrivateKey());

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
        var root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "AI00", "Connector");
        var sid = WindowsIdentity.GetCurrent().User?.Value
            ?? throw new InvalidOperationException("windows_sid_unavailable");
        if (!values.TryGetValue("--ticket-uri", out var ticket) ||
            !Uri.TryCreate(ticket, UriKind.Absolute, out var ticketUri))
            throw new InvalidOperationException(
                "Usage: AI00.Connector.Service.exe pair --ticket-uri ai00connector://pair?...");
        using var http = new HttpClient();
        await HandleUriAsync(ticketUri, http, root, sid, cancellationToken);
        var gateway = ParseQuery(ticketUri.Query)["gateway"].TrimEnd('/');
        Environment.SetEnvironmentVariable(
            "Connector__GatewayUrl", gateway, EnvironmentVariableTarget.Machine);
        Console.WriteLine("AI00 Connector pairing completed.");
    }

    public static async Task HandleUriAsync(
        Uri ticketUri, HttpClient http, string root, string windowsSid,
        CancellationToken cancellationToken = default)
    {
        if (!string.Equals(ticketUri.Scheme, "ai00connector", StringComparison.OrdinalIgnoreCase) ||
            !string.Equals(ticketUri.Host, "pair", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("connector_pairing_uri_invalid");
        var query = ParseQuery(ticketUri.Query);
        if (!query.TryGetValue("gateway", out var gateway) ||
            !Uri.TryCreate(gateway, UriKind.Absolute, out var gatewayUri) ||
            (gatewayUri.Scheme != Uri.UriSchemeHttps && !gatewayUri.IsLoopback))
            throw new InvalidOperationException("connector_pairing_gateway_untrusted");
        if (!query.TryGetValue("bootstrap_id", out var bootstrapId) || string.IsNullOrWhiteSpace(bootstrapId) ||
            !query.TryGetValue("bootstrap_token", out var bootstrapToken) || string.IsNullOrWhiteSpace(bootstrapToken))
            throw new InvalidOperationException("connector_bootstrap_ticket_invalid");

        Directory.CreateDirectory(root);
        var installationPath = Path.Combine(root, "installation.id");
        var installationId = File.Exists(installationPath)
            ? File.ReadAllText(installationPath).Trim()
            : "installation-" + Guid.NewGuid().ToString("N");
        if (!File.Exists(installationPath)) File.WriteAllText(installationPath, installationId);
        var sidHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(windowsSid))).ToLowerInvariant();
        var user = Environment.UserName;
        var maskedUser = user.Length <= 2 ? "**" : $"{user[0]}***{user[^1]}";
        http.BaseAddress ??= new Uri(gateway.TrimEnd('/') + "/");
        var pendingStore = new PendingPairingStore(Path.Combine(root, "pending.pairing"));
        var pending = pendingStore.Load();
        if (pending is not null && pending.ExpiresAt <= DateTimeOffset.UtcNow)
        {
            pendingStore.Delete();
            pending = null;
        }
        if (pending is not null && pending.BootstrapId != bootstrapId)
            throw new InvalidOperationException("connector_pairing_in_progress");

        using var pairing = pending is null
            ? BrowserPairingSession.Create(
                installationId, Environment.MachineName, "1.0.0", sidHash, maskedUser, bootstrapToken)
            : BrowserPairingSession.Restore(
                new BrowserPairingRequest(
                    bootstrapToken, pending.InstallationId,
                    Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(pending.Verifier))).ToLowerInvariant(),
                    Environment.MachineName, "1.0.0", sidHash, maskedUser, "pending"),
                pending.Verifier, pending.PrivateKeyPkcs8);
        pending ??= new PendingPairing(
            bootstrapId, "", installationId, pairing.Verifier, pairing.ExportPrivateKey(),
            gateway.TrimEnd('/'), DateTimeOffset.UtcNow.AddMinutes(2));
        pendingStore.Save(pending);

        PairingCreated created;
        if (string.IsNullOrWhiteSpace(pending.PairingId))
        {
            using var pairingRequest = new HttpRequestMessage(HttpMethod.Post, "api/v1/simulation/connectors/pairings") {
                Content = JsonContent.Create(pairing.Request),
            };
            pairingRequest.Headers.TryAddWithoutValidation("Idempotency-Key", bootstrapId);
            using var response = await http.SendAsync(pairingRequest, cancellationToken);
            response.EnsureSuccessStatusCode();
            created = (await response.Content.ReadFromJsonAsync<ApiEnvelope<PairingCreated>>(
                cancellationToken: cancellationToken))?.Data
                ?? throw new InvalidOperationException("connector_pairing_response_invalid");
            if (created.BootstrapId != bootstrapId)
                throw new InvalidOperationException("connector_bootstrap_response_mismatch");
            pending = pending with { PairingId = created.PairingId, ExpiresAt = created.ExpiresAt };
            pendingStore.Save(pending);
        }
        else
        {
            created = new PairingCreated(pending.PairingId, "", "", pending.ExpiresAt, bootstrapId);
        }

        BrowserPairingCompletion? completion = null;
        while (DateTimeOffset.UtcNow < created.ExpiresAt && !cancellationToken.IsCancellationRequested)
        {
            using var complete = await http.PostAsJsonAsync(
                $"api/v1/simulation/connectors/pairings/{created.PairingId}/complete",
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
        if (credential.InstallationId != installationId)
            throw new InvalidOperationException("connector_installation_mismatch");
        if (string.IsNullOrWhiteSpace(credential.ActivationProof))
            throw new InvalidOperationException("connector_activation_proof_missing");
        var credentialPath = Path.Combine(root, "device.credential");
        var credentialStore = new DeviceCredentialStore(credentialPath);
        credentialStore.Save(new(
            credential.ConnectorId, credential.UserId, windowsSid, credential.ConnectorToken));
        ProtectedSecretStore.Save(
            Path.Combine(root, "operation.keys"),
            new Dictionary<string, string> { [credential.PlanSigningKeyId] = credential.PlanSigningSecret });
        var stored = credentialStore.Load();
        var storedKeys = ProtectedSecretStore.Load(Path.Combine(root, "operation.keys"));
        if (stored.DeviceId != credential.ConnectorId || stored.UserId != credential.UserId ||
            stored.WindowsSid != windowsSid || stored.DeviceToken != credential.ConnectorToken ||
            storedKeys.GetValueOrDefault(credential.PlanSigningKeyId) != credential.PlanSigningSecret)
            throw new InvalidOperationException("connector_credential_readback_failed");
        using var activate = await http.PostAsJsonAsync(
            $"api/v1/simulation/connectors/pairings/{created.PairingId}/activate",
            new { connector_id = credential.ConnectorId, activation_proof = credential.ActivationProof },
            cancellationToken);
        activate.EnsureSuccessStatusCode();
        pendingStore.Delete();
    }

    private static Dictionary<string, string> ParseQuery(string value) => value
        .TrimStart('?')
        .Split('&', StringSplitOptions.RemoveEmptyEntries)
        .Select(item => item.Split('=', 2))
        .Where(item => item.Length == 2)
        .ToDictionary(
            item => Uri.UnescapeDataString(item[0]), item => Uri.UnescapeDataString(item[1]),
            StringComparer.Ordinal);

    private sealed record ApiEnvelope<T>(bool Success, T Data);
    private sealed record PairingCreated(
        [property: JsonPropertyName("pairing_id")] string PairingId,
        [property: JsonPropertyName("user_code")] string UserCode,
        [property: JsonPropertyName("verification_uri")] string VerificationUri,
        [property: JsonPropertyName("expires_at")] DateTimeOffset ExpiresAt,
        [property: JsonPropertyName("bootstrap_id")] string BootstrapId);
    private sealed record BrowserPairingCompletion(
        [property: JsonPropertyName("connector_id")] string ConnectorId,
        [property: JsonPropertyName("encrypted_credential_envelope")] string EncryptedCredentialEnvelope,
        [property: JsonPropertyName("envelope_hash")] string EnvelopeHash,
        [property: JsonPropertyName("activation_challenge")] string ActivationChallenge);
}
