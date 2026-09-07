using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Service;

public static class SessionHostBrokerClient
{
    public static async Task EnsureStartedAsync(
        SessionHostStartRequest request, CancellationToken cancellationToken)
    {
        await using var pipe = new NamedPipeClientStream(
            ".", ConnectorPipeName.SessionBrokerFor(request.WindowsSid), PipeDirection.InOut,
            PipeOptions.Asynchronous);
        await pipe.ConnectAsync(5_000, cancellationToken);
        await using var writer = new StreamWriter(pipe, new UTF8Encoding(false), leaveOpen: true)
        {
            AutoFlush = true,
        };
        using var reader = new StreamReader(pipe, Encoding.UTF8, leaveOpen: true);
        await writer.WriteLineAsync(
            JsonSerializer.Serialize(request).AsMemory(), cancellationToken);
        if (await reader.ReadLineAsync(cancellationToken) != "ok")
            throw new ConnectorException("session_host_start_failed");
    }
}
