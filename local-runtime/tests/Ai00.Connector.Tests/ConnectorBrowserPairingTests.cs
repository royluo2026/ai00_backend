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
}
