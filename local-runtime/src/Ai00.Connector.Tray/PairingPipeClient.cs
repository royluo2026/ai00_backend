using System.IO.Pipes;
using System.Security.Principal;
using System.Text;

namespace Ai00.Connector.Tray;

public static class PairingPipeClient
{
    public const string PipeName = "ai00-connector-pairing-v1";

    public static bool IsAllowed(Uri uri)
    {
        if (!string.Equals(uri.Scheme, "ai00connector", StringComparison.OrdinalIgnoreCase) ||
            !string.Equals(uri.Host, "pair", StringComparison.OrdinalIgnoreCase) ||
            uri.OriginalString.Length > 8 * 1024)
            return false;
        var values = uri.Query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries)
            .Select(item => item.Split('=', 2))
            .Where(item => item.Length == 2)
            .ToDictionary(item => Uri.UnescapeDataString(item[0]), item => Uri.UnescapeDataString(item[1]));
        return values.TryGetValue("gateway", out var gateway) &&
            Uri.TryCreate(gateway, UriKind.Absolute, out var gatewayUri) &&
            (gatewayUri.Scheme == Uri.UriSchemeHttps || gatewayUri.IsLoopback) &&
            values.TryGetValue("bootstrap_id", out var bootstrapId) && !string.IsNullOrWhiteSpace(bootstrapId) &&
            values.TryGetValue("bootstrap_token", out var bootstrapToken) && !string.IsNullOrWhiteSpace(bootstrapToken);
    }

    public static async Task ForwardAsync(Uri uri, CancellationToken cancellationToken = default)
    {
        if (!IsAllowed(uri)) throw new InvalidOperationException("connector_pairing_uri_invalid");
        await using var pipe = new NamedPipeClientStream(
            ".", PipeName, PipeDirection.InOut, PipeOptions.Asynchronous,
            TokenImpersonationLevel.Impersonation);
        await pipe.ConnectAsync(5_000, cancellationToken);
        await using var writer = new StreamWriter(pipe, new UTF8Encoding(false), leaveOpen: true) {
            AutoFlush = true,
        };
        await writer.WriteLineAsync(uri.OriginalString.AsMemory(), cancellationToken);
        using var reader = new StreamReader(pipe, Encoding.UTF8, leaveOpen: true);
        var result = await reader.ReadLineAsync(cancellationToken);
        if (result != "ok") throw new InvalidOperationException(result ?? "connector_pairing_service_unavailable");
    }
}
