using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Ai00.Connector.Service;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class ConnectorBrowserPairingTests
{
    [Fact]
    public void RequestContainsProofAndEphemeralKeyButNoFeishuCredential()
    {
        using var session = BrowserPairingSession.Create(
            "installation-1", "Workstation A", "1.0.0", new string('a', 64), "DOMAIN\\u***");

        var json = JsonSerializer.Serialize(session.Request);

        Assert.Contains("verifier_hash", json);
        Assert.Contains("ephemeral_public_key", json);
        Assert.DoesNotContain("feishu", json, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(session.Verifier, json);
    }

    [Fact]
    public void EncryptedEnvelopeDecryptsOnlyInsideOriginalPairingSession()
    {
        using var session = BrowserPairingSession.Create(
            "installation-1", "Workstation A", "1.0.0", new string('a', 64), "DOMAIN\\u***");
        using var publicKey = RSA.Create();
        publicKey.ImportFromPem(session.PublicKeyPem);
        var clear = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
        {
            connector_id = "connector-1",
            connector_token = "connector-secret",
            bound_user_id = "user-1",
            team_id = "team-1",
            plan_signing_key_id = "plan-key.device.1",
            plan_signing_secret = new string('s', 64),
        }));
        var envelopeKey = RandomNumberGenerator.GetBytes(32);
        var nonce = RandomNumberGenerator.GetBytes(12);
        var cipher = new byte[clear.Length];
        var tag = new byte[16];
        using (var aes = new AesGcm(envelopeKey, 16))
            aes.Encrypt(nonce, clear, cipher, tag);
        var encryptedKey = publicKey.Encrypt(envelopeKey, RSAEncryptionPadding.OaepSHA256);
        var envelope = Convert.ToBase64String(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
        {
            encrypted_key = Convert.ToBase64String(encryptedKey),
            nonce = Convert.ToBase64String(nonce),
            ciphertext = Convert.ToBase64String(cipher),
            tag = Convert.ToBase64String(tag),
        })));

        var credential = session.Decrypt(envelope);

        Assert.Equal("connector-1", credential.ConnectorId);
        Assert.Equal("connector-secret", credential.ConnectorToken);
        Assert.Equal("user-1", credential.UserId);
        Assert.Equal("plan-key.device.1", credential.PlanSigningKeyId);
    }

    [Fact]
    public void PersistedPrivateKeyRestoresTheSamePairingSession()
    {
        using var original = BrowserPairingSession.Create(
            "installation-1", "Workstation A", "1.0.0", new string('a', 64), "DOMAIN\\u***",
            "bootstrap-secret");

        using var restored = BrowserPairingSession.Restore(original.Request, original.Verifier, original.ExportPrivateKey());

        Assert.Equal(original.PublicKeyPem, restored.PublicKeyPem);
        Assert.Equal("bootstrap-secret", restored.Request.BootstrapToken);
    }

    [Fact]
    public async Task TicketFlowActivatesOnlyAfterCredentialReadBack()
    {
        var root = Path.Combine(Path.GetTempPath(), "ai00-connector-pairing", Guid.NewGuid().ToString("N"));
        var handler = new PairingHandler();
        using var http = new HttpClient(handler) { BaseAddress = new Uri("http://127.0.0.1:8080/") };
        var ticket = new Uri(
            "ai00connector://pair?gateway=http%3A%2F%2F127.0.0.1%3A8080" +
            "&bootstrap_id=bootstrap-1&bootstrap_token=bootstrap-secret");

        try
        {
            await ConnectorPairing.HandleUriAsync(ticket, http, root, "S-1-5-21-test");

            Assert.Equal("bootstrap-secret", handler.Request?.BootstrapToken);
            Assert.True(handler.Activated);
            Assert.Equal("connector-1", new DeviceCredentialStore(
                Path.Combine(root, "device.credential")).Load().DeviceId);
            Assert.Null(new PendingPairingStore(Path.Combine(root, "pending.pairing")).Load());
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, true);
        }
    }

    [Fact]
    public async Task TicketFlowRejectsCredentialForAnotherInstallation()
    {
        var root = Path.Combine(Path.GetTempPath(), "ai00-connector-pairing", Guid.NewGuid().ToString("N"));
        var handler = new PairingHandler { CredentialInstallationId = "another-installation" };
        using var http = new HttpClient(handler) { BaseAddress = new Uri("http://127.0.0.1:8080/") };
        var ticket = new Uri(
            "ai00connector://pair?gateway=http%3A%2F%2F127.0.0.1%3A8080" +
            "&bootstrap_id=bootstrap-1&bootstrap_token=bootstrap-secret");

        try
        {
            var error = await Assert.ThrowsAsync<InvalidOperationException>(() =>
                ConnectorPairing.HandleUriAsync(ticket, http, root, "S-1-5-21-test"));
            Assert.Equal("connector_installation_mismatch", error.Message);
            Assert.False(handler.Activated);
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, true);
        }
    }

    [Fact]
    public async Task TicketFlowRejectsAResponseForAnotherBootstrap()
    {
        var root = Path.Combine(Path.GetTempPath(), "ai00-connector-pairing", Guid.NewGuid().ToString("N"));
        var handler = new PairingHandler { ResponseBootstrapId = "bootstrap-other" };
        using var http = new HttpClient(handler) { BaseAddress = new Uri("http://127.0.0.1:8080/") };
        var ticket = new Uri(
            "ai00connector://pair?gateway=http%3A%2F%2F127.0.0.1%3A8080" +
            "&bootstrap_id=bootstrap-1&bootstrap_token=bootstrap-secret");

        try
        {
            var error = await Assert.ThrowsAsync<InvalidOperationException>(() =>
                ConnectorPairing.HandleUriAsync(ticket, http, root, "S-1-5-21-test"));
            Assert.Equal("connector_bootstrap_response_mismatch", error.Message);
            Assert.False(handler.Activated);
        }
        finally
        {
            if (Directory.Exists(root)) Directory.Delete(root, true);
        }
    }

    private sealed class PairingHandler : HttpMessageHandler
    {
        public BrowserPairingRequest? Request { get; private set; }
        public bool Activated { get; private set; }
        public string? CredentialInstallationId { get; init; }
        public string ResponseBootstrapId { get; init; } = "bootstrap-1";

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (request.RequestUri?.AbsolutePath.EndsWith("/pairings", StringComparison.Ordinal) == true)
            {
                Request = await request.Content!.ReadFromJsonAsync<BrowserPairingRequest>(cancellationToken);
                return Json(new { success = true, data = new {
                    pairing_id = "pair-1", user_code = "hidden", verification_uri = "/unused",
                    bootstrap_id = ResponseBootstrapId,
                    expires_at = DateTimeOffset.UtcNow.AddMinutes(2),
                }});
            }
            if (request.RequestUri?.AbsolutePath.EndsWith("/complete", StringComparison.Ordinal) == true)
                return Json(new { success = true, data = new {
                    connector_id = "connector-1", encrypted_credential_envelope = Encrypt(Request!),
                    envelope_hash = "sha256:" + new string('a', 64), activation_challenge = "",
                }});
            if (request.RequestUri?.AbsolutePath.EndsWith("/activate", StringComparison.Ordinal) == true)
            {
                var body = await request.Content!.ReadFromJsonAsync<Dictionary<string, string>>(cancellationToken);
                Activated = body?["connector_id"] == "connector-1" && body["activation_proof"] == "activation-secret";
                return Json(new { success = true, data = new { status = "active" } });
            }
            return new HttpResponseMessage(HttpStatusCode.NotFound);
        }

        private static HttpResponseMessage Json(object value) => new(HttpStatusCode.OK) {
            Content = JsonContent.Create(value),
        };

        private string Encrypt(BrowserPairingRequest pairing)
        {
            using var publicKey = RSA.Create();
            publicKey.ImportFromPem(pairing.EphemeralPublicKey);
            var clear = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new {
                connector_id = "connector-1", connector_token = "connector-secret",
                installation_id = CredentialInstallationId ?? pairing.InstallationId,
                bound_user_id = "user-1", team_id = "team-1", activation_proof = "activation-secret",
                plan_signing_key_id = "plan-key.device.1", plan_signing_secret = new string('s', 64),
            }));
            var key = RandomNumberGenerator.GetBytes(32);
            var nonce = RandomNumberGenerator.GetBytes(12);
            var cipher = new byte[clear.Length];
            var tag = new byte[16];
            using (var aes = new AesGcm(key, 16)) aes.Encrypt(nonce, clear, cipher, tag);
            var envelope = JsonSerializer.Serialize(new {
                encrypted_key = Convert.ToBase64String(publicKey.Encrypt(key, RSAEncryptionPadding.OaepSHA256)),
                nonce = Convert.ToBase64String(nonce), ciphertext = Convert.ToBase64String(cipher),
                tag = Convert.ToBase64String(tag),
            });
            CryptographicOperations.ZeroMemory(clear);
            CryptographicOperations.ZeroMemory(key);
            return Convert.ToBase64String(Encoding.UTF8.GetBytes(envelope));
        }
    }
}
