using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Tray;

public sealed class SessionHostBroker(string windowsSid)
{
    public static bool IsAllowed(SessionHostStartRequest? request, string expectedSid) =>
        request is not null &&
        !string.IsNullOrWhiteSpace(request.DeviceId) &&
        !string.IsNullOrWhiteSpace(request.UserId) &&
        string.Equals(request.WindowsSid, expectedSid, StringComparison.Ordinal);

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            var security = new System.IO.Pipes.PipeSecurity();
            security.AddAccessRule(new PipeAccessRule(
                WindowsIdentity.GetCurrent().User!, PipeAccessRights.ReadWrite, AccessControlType.Allow));
            security.AddAccessRule(new PipeAccessRule(
                new SecurityIdentifier(WellKnownSidType.LocalServiceSid, null),
                PipeAccessRights.ReadWrite, AccessControlType.Allow));
            await using var pipe = NamedPipeServerStreamAcl.Create(
                ConnectorPipeName.SessionBrokerFor(windowsSid), PipeDirection.InOut, 1,
                PipeTransmissionMode.Byte, PipeOptions.Asynchronous, 256, 256, security);
            await pipe.WaitForConnectionAsync(cancellationToken);
            using var reader = new StreamReader(pipe, Encoding.UTF8, leaveOpen: true);
            await using var writer = new StreamWriter(pipe, new UTF8Encoding(false), leaveOpen: true)
            {
                AutoFlush = true,
            };
            SessionHostStartRequest? request = null;
            try
            {
                request = JsonSerializer.Deserialize<SessionHostStartRequest>(
                    await reader.ReadLineAsync(cancellationToken) ?? "");
            }
            catch (JsonException) { }
            if (!IsAllowed(request, windowsSid))
            {
                await writer.WriteLineAsync("invalid".AsMemory(), cancellationToken);
                continue;
            }
            try
            {
                SessionHostProcess.EnsureStarted(request!);
                await writer.WriteLineAsync("ok".AsMemory(), cancellationToken);
            }
            catch
            {
                await writer.WriteLineAsync("failed".AsMemory(), cancellationToken);
            }
        }
    }
}
