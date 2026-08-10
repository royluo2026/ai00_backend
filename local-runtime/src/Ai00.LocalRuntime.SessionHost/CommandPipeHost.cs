using System.IO.Pipes;
using System.Text.Json;
using Ai00.LocalRuntime.Contracts;

namespace Ai00.LocalRuntime.SessionHost;

public sealed class CommandPipeHost(CommandDispatcher dispatcher, string pipeSecret)
{
    public async Task RunAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            await using var pipe = new NamedPipeServerStream("ai00-local-runtime-v1", PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous, 64 * 1024, 64 * 1024);
            await pipe.WaitForConnectionAsync(cancellationToken);
            var envelope = await JsonSerializer.DeserializeAsync<PipeCommand>(pipe, cancellationToken: cancellationToken);
            var completion = envelope is null || !PipeSecurity.Verify(envelope, pipeSecret)
                ? new CommandCompletion("", false, Error: "Invalid or unauthenticated pipe command")
                : await dispatcher.ExecuteAsync(envelope.Command);
            await JsonSerializer.SerializeAsync(pipe, completion, cancellationToken: cancellationToken);
            await pipe.FlushAsync(cancellationToken);
        }
    }
}
