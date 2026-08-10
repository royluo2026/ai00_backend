using System.IO.Pipes;
using System.Text.Json;
using Ai00.LocalRuntime.Contracts;

namespace Ai00.LocalRuntime.SessionHost;

public sealed class CommandPipeHost(CommandDispatcher dispatcher, IReadOnlyDictionary<string, string> signingKeys)
{
    public async Task RunAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            await using var pipe = new NamedPipeServerStream("ai00-local-runtime-v2", PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly, 64 * 1024, 64 * 1024);
            await pipe.WaitForConnectionAsync(cancellationToken);
            var request = await JsonSerializer.DeserializeAsync<LocalExecutionRequest>(pipe, cancellationToken: cancellationToken);
            var completion = request is null || !PipeSecurity.Verify(request.Lease, signingKeys)
                ? new OperationCompletion("invalid", "failed", ErrorCode: "invalid_operation_signature")
                : await dispatcher.ExecuteAsync(request.Lease.Operation, request.MaterializedArtifacts);
            await JsonSerializer.SerializeAsync(pipe, completion, cancellationToken: cancellationToken);
            await pipe.FlushAsync(cancellationToken);
        }
    }
}
