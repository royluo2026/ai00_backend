using System.IO.Pipes;
using System.Text.Json;
using Ai00.Connector.Contracts;
using ContractPipeSecurity = Ai00.Connector.Contracts.PipeSecurity;

namespace Ai00.Connector.SessionHost;

public sealed class CommandPipeHost(CommandDispatcher dispatcher, IReadOnlyDictionary<string, string> signingKeys, string pipeName)
{
    public async Task RunAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            await using var pipe = new NamedPipeServerStream(pipeName, PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly, 64 * 1024, 64 * 1024);
            await pipe.WaitForConnectionAsync(cancellationToken);
            var request = await JsonSerializer.DeserializeAsync<LocalExecutionRequest>(pipe, cancellationToken: cancellationToken);
            OperationCompletion completion;
            if (request is null || !ContractPipeSecurity.Verify(request.Lease, signingKeys))
            {
                completion = new OperationCompletion("invalid", "failed", ErrorCode: "invalid_operation_signature");
            }
            else
            {
                completion = await dispatcher.ExecuteAsync(request.Lease.Operation, request.MaterializedArtifacts);
            }
            await JsonSerializer.SerializeAsync(pipe, completion, cancellationToken: cancellationToken);
            await pipe.FlushAsync(cancellationToken);
        }
    }
}
