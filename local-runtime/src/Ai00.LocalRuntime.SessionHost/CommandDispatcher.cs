using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Ai00.LocalRuntime.Contracts;

namespace Ai00.LocalRuntime.SessionHost;

public sealed class CommandDispatcher(VisMockupAdapter visMockup, CommandLedger ledger)
{
    public async Task<CommandCompletion> ExecuteAsync(CommandEnvelope command)
    {
        if (!ledger.TryBegin(command.CommandId, out var existingState)) return new(command.LeaseId, existingState == "completed", new { duplicate = true, state = existingState }, existingState == "completed" ? "" : "Prior execution did not complete; refusing unsafe replay");
        if (!RuntimeCapabilities.Allowed.Contains(command.Capability)) return new(command.LeaseId, false, Error: "Capability is not whitelisted");
        var canonical = JsonSerializer.Serialize(command.Payload, new JsonSerializerOptions { WriteIndented = false });
        var actualHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(canonical))).ToLowerInvariant();
        if (!string.Equals(actualHash, command.PayloadHash, StringComparison.OrdinalIgnoreCase)) return new(command.LeaseId, false, Error: "Payload hash mismatch");
        try
        {
            object result = command.Capability switch
            {
                "vismockup.status" => await visMockup.StatusAsync(),
                "vismockup.launch" => await visMockup.LaunchAsync(),
                "vismockup.open_file" => await visMockup.OpenFileAsync(command.Payload.GetProperty("file_path").GetString() ?? ""),
                "vismockup.visibility" => await visMockup.VisibilityAsync(command.Payload.GetProperty("action").GetString() ?? ""),
                "vismockup.capture" => await visMockup.CaptureAsync(),
                _ => throw new InvalidOperationException("Capability has no adapter")
            };
            ledger.Complete(command.CommandId);
            return new(command.LeaseId, true, result);
        }
        catch (Exception ex) { return new(command.LeaseId, false, Error: ex.Message[..Math.Min(ex.Message.Length, 1000)]); }
    }
}
