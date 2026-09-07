using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;

namespace Ai00.Connector.Service;

public sealed class PairingPipeHost(
    IHttpClientFactory httpClients,
    ILogger<PairingPipeHost> logger) : BackgroundService
{
    public const string PipeName = "ai00-connector-pairing-v1";
    private const int MaximumMessageBytes = 8 * 1024;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await ServeOnceAsync(stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception error)
            {
                logger.LogWarning(error, "Connector pairing pipe request failed");
            }
        }
    }

    private async Task ServeOnceAsync(CancellationToken cancellationToken)
    {
        var security = new PipeSecurity();
        security.AddAccessRule(new PipeAccessRule(
            new SecurityIdentifier(WellKnownSidType.BuiltinUsersSid, null),
            PipeAccessRights.FullControl,
            AccessControlType.Allow));
        security.AddAccessRule(new PipeAccessRule(
            new SecurityIdentifier(WellKnownSidType.LocalServiceSid, null),
            PipeAccessRights.FullControl, AccessControlType.Allow));
        security.AddAccessRule(new PipeAccessRule(
            new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null),
            PipeAccessRights.FullControl, AccessControlType.Allow));
        await using var pipe = NamedPipeServerStreamAcl.Create(
            PipeName, PipeDirection.InOut, 1, PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous, MaximumMessageBytes, MaximumMessageBytes, security);
        await pipe.WaitForConnectionAsync(cancellationToken);
        var callerSid = "";
        var callerIsInteractive = false;
        pipe.RunAsClient(() =>
        {
            using var identity = WindowsIdentity.GetCurrent();
            callerSid = identity.User?.Value ?? "";
            callerIsInteractive = new WindowsPrincipal(identity).IsInRole(
                new SecurityIdentifier(WellKnownSidType.InteractiveSid, null));
        });
        if (string.IsNullOrWhiteSpace(callerSid) || !callerIsInteractive)
            throw new InvalidOperationException("connector_pairing_caller_unavailable");
        try
        {
            var value = await ReadMessageAsync(pipe, cancellationToken);
            if (!Uri.TryCreate(value, UriKind.Absolute, out var uri))
                throw new InvalidOperationException("connector_pairing_uri_invalid");
            var root = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                "AI00", "Connector");
            using var http = httpClients.CreateClient(nameof(PairingPipeHost));
            await ConnectorPairing.HandleUriAsync(uri, http, root, callerSid, cancellationToken);
            await WriteResultAsync(pipe, "ok", cancellationToken);
        }
        catch (Exception error)
        {
            logger.LogWarning(error, "Connector pairing failed for caller {CallerSid}", callerSid);
            await WriteResultAsync(pipe, "connector_pairing_failed", cancellationToken);
        }
    }

    private static async Task<string> ReadMessageAsync(Stream stream, CancellationToken cancellationToken)
    {
        var buffer = new byte[MaximumMessageBytes + 1];
        var length = 0;
        while (length < buffer.Length)
        {
            var count = await stream.ReadAsync(buffer.AsMemory(length, 1), cancellationToken);
            if (count == 0 || buffer[length] == (byte)'\n') break;
            length += count;
        }
        if (length > MaximumMessageBytes)
            throw new InvalidOperationException("connector_pairing_message_too_large");
        return Encoding.UTF8.GetString(buffer, 0, length).TrimEnd('\r');
    }

    private static async Task WriteResultAsync(
        Stream stream, string value, CancellationToken cancellationToken)
    {
        var bytes = Encoding.UTF8.GetBytes(value + "\n");
        await stream.WriteAsync(bytes, cancellationToken);
        await stream.FlushAsync(cancellationToken);
    }
}
