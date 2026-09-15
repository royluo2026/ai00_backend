using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Ai00.Connector.Adapters.VisMockup;
using Microsoft.Extensions.Hosting;

namespace Ai00.Connector.AppHost;

public sealed record TeamcenterLoginCommand(string RequestId, string EndpointId, string Username, string Password);

public static class TeamcenterControlProtocol
{
    public const int MaximumBytes = 4096;
    public static TeamcenterLoginCommand ParseRequest(string json)
    {
        if (Encoding.UTF8.GetByteCount(json) > MaximumBytes) throw new InvalidDataException("teamcenter_control_size_invalid");
        using var document = JsonDocument.Parse(json, new JsonDocumentOptions { MaxDepth = 2 });
        var value = document.RootElement;
        var fields = value.EnumerateObject().Select(item => item.Name).ToArray();
        var expected = new[] { "type", "request_id", "endpoint_id", "username", "password" };
        if (fields.Length != expected.Length || fields.Distinct().Count() != fields.Length || fields.Except(expected).Any()
            || value.GetProperty("type").GetString() != "teamcenter_login")
            throw new InvalidDataException("teamcenter_control_message_forbidden");
        var requestId = value.GetProperty("request_id").GetString() ?? "";
        var endpoint = value.GetProperty("endpoint_id").GetString() ?? "";
        var username = value.GetProperty("username").GetString() ?? "";
        var password = value.GetProperty("password").GetString() ?? "";
        if (!Regex.IsMatch(requestId, "\\Atc-[a-f0-9]{32}\\z") || endpoint != "tc-production"
            || username.Length is < 1 or > 191 || password.Length is < 1 or > 1024
            || username.IndexOfAny(['\r','\n']) >= 0 || password.IndexOfAny(['\r','\n']) >= 0)
            throw new InvalidDataException("teamcenter_control_message_invalid");
        return new(requestId, endpoint, username, password);
    }

    public static string Result(string requestId, bool success, string code)
    {
        if (!Regex.IsMatch(requestId, "\\Atc-[a-f0-9]{32}\\z")
            || !Regex.IsMatch(code, "\\A[a-z][a-z0-9_]{1,63}\\z"))
            throw new InvalidDataException("teamcenter_control_result_invalid");
        return JsonSerializer.Serialize(new { type = "teamcenter_login_result", request_id = requestId,
            state = success ? "ready" : "failed", code });
    }
}

// Separate from the diagnostic pipe: business credentials can never enter diagnostics.
// The current-user ACL and peer PID check bind this control channel to the Electron parent.
public sealed class TeamcenterControlPipeHost(AppHostOptions options, TeamcenterReadOnlyRuntime runtime) : BackgroundService
{
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetNamedPipeClientProcessId(Microsoft.Win32.SafeHandles.SafePipeHandle pipe, out uint pid);
    [StructLayout(LayoutKind.Sequential)]
    private struct SecurityAttributes { public int Size; public IntPtr Descriptor; public int Inherit; }
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool ConvertStringSecurityDescriptorToSecurityDescriptorW(string text, uint revision, out IntPtr descriptor, out uint length);
    [DllImport("kernel32.dll")] private static extern IntPtr LocalFree(IntPtr pointer);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern Microsoft.Win32.SafeHandles.SafePipeHandle CreateNamedPipeW(string name, uint openMode, uint pipeMode,
        uint maxInstances, uint outputSize, uint inputSize, uint timeout, ref SecurityAttributes security);

    private NamedPipeServerStream CreatePipe()
    {
        var sid = System.Security.Principal.WindowsIdentity.GetCurrent().User!.Value;
        if (!ConvertStringSecurityDescriptorToSecurityDescriptorW("D:P(A;;GA;;;" + sid + ")", 1, out var descriptor, out _))
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        try
        {
            var security = new SecurityAttributes { Size = Marshal.SizeOf<SecurityAttributes>(), Descriptor = descriptor };
            var handle = CreateNamedPipeW("\\\\.\\pipe\\" + options.PipeName + ".Teamcenter", 0x40080003, 0x8, 1,
                TeamcenterControlProtocol.MaximumBytes, TeamcenterControlProtocol.MaximumBytes, 0, ref security);
            if (handle.IsInvalid) { handle.Dispose(); throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()); }
            return new NamedPipeServerStream(PipeDirection.InOut, true, false, handle);
        }
        finally { LocalFree(descriptor); }
    }

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                using var pipe = CreatePipe();
                await pipe.WaitForConnectionAsync(ct);
                if (!GetNamedPipeClientProcessId(pipe.SafePipeHandle, out var pid) || pid != options.ParentPid)
                    throw new InvalidDataException("teamcenter_control_parent_mismatch");
                var attempts = new Queue<DateTimeOffset>();
                while (pipe.IsConnected && !ct.IsCancellationRequested)
                {
                    var command = TeamcenterControlProtocol.ParseRequest(await ReadAsync(pipe, ct));
                    var now = DateTimeOffset.UtcNow;
                    while (attempts.Count > 0 && now - attempts.Peek() > TimeSpan.FromMinutes(1)) attempts.Dequeue();
                    if (attempts.Count >= 5) { await WriteAsync(pipe, TeamcenterControlProtocol.Result(command.RequestId, false, "rate_limited"), ct); continue; }
                    attempts.Enqueue(now);
                    try
                    {
                        await runtime.LoginAsync(command.EndpointId, command.Username, command.Password, ct);
                        await WriteAsync(pipe, TeamcenterControlProtocol.Result(command.RequestId, true, "ready"), ct);
                    }
                    catch (Exception error)
                    {
                        var code = error.Message is "teamcenter_authentication_failed" or "teamcenter_runtime_unavailable"
                            ? error.Message : "teamcenter_login_failed";
                        await WriteAsync(pipe, TeamcenterControlProtocol.Result(command.RequestId, false, code), ct);
                    }
                }
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { }
            catch (IOException) { }
            catch (InvalidDataException) { await Task.Delay(250, ct); }
        }
    }

    private static async Task<string> ReadAsync(Stream stream, CancellationToken ct)
    {
        var bytes = new byte[TeamcenterControlProtocol.MaximumBytes]; var one = new byte[1]; var length = 0;
        while (true) { if (await stream.ReadAsync(one, ct) == 0) throw new EndOfStreamException();
            if (one[0] == 10) break; if (length == bytes.Length) throw new InvalidDataException("teamcenter_control_size_invalid");
            bytes[length++] = one[0]; }
        return new UTF8Encoding(false, true).GetString(bytes, 0, length);
    }

    private static async Task WriteAsync(Stream stream, string value, CancellationToken ct)
    { await stream.WriteAsync(Encoding.UTF8.GetBytes(value + "\n"), ct); await stream.FlushAsync(ct); }
}
