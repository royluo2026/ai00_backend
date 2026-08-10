using System.IO.Pipes;
using System.Text.Json;
using Ai00.LocalRuntime.Contracts;
using Microsoft.Extensions.Options;

namespace Ai00.LocalRuntime.Service;

public sealed class SessionHostClient(IOptions<RuntimeOptions> options)
{
    public async Task<CommandCompletion> ExecuteAsync(CommandEnvelope command, CancellationToken cancellationToken)
    {
        if (!RuntimeCapabilities.Allowed.Contains(command.Capability))
            return new(command.LeaseId, false, Error: "Capability is not in the runtime whitelist");
        if (command.ExpiresAt <= DateTimeOffset.UtcNow)
            return new(command.LeaseId, false, Error: "Command expired before execution");

        await using var pipe = new NamedPipeClientStream(".", "ai00-local-runtime-v1", PipeDirection.InOut, PipeOptions.Asynchronous);
        await pipe.ConnectAsync(5_000, cancellationToken);
        var envelope = new PipeCommand(command, PipeSecurity.Sign(command, options.Value.PipeSecret));
        await JsonSerializer.SerializeAsync(pipe, envelope, cancellationToken: cancellationToken);
        await pipe.FlushAsync(cancellationToken);
        var result = await JsonSerializer.DeserializeAsync<CommandCompletion>(pipe, cancellationToken: cancellationToken);
        return result ?? new(command.LeaseId, false, Error: "Session Host returned no result");
    }
}
