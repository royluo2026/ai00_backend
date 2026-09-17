using System.Diagnostics;
using System.Text;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

internal interface ITeamcenterVisualizationLauncher
{
    Task LaunchAsync(string materialPath, CancellationToken ct);
}

internal sealed class TeamcenterVisualizationRunner(
    string executable = @"D:\Siemens\Teamcenter14\portal\runner.exe") : ITeamcenterVisualizationLauncher
{
    internal static string EncodePath(string path) =>
        Convert.ToHexString(Encoding.BigEndianUnicode.GetBytes(Path.GetFullPath(path)));

    internal ProcessStartInfo CreateStartInfo(string materialPath)
    {
        var fullPath = Path.GetFullPath(materialPath);
        if (!File.Exists(fullPath) || !string.Equals(Path.GetExtension(fullPath), ".vvi", StringComparison.OrdinalIgnoreCase))
            throw new ConnectorNoEffectException("teamcenter_visualization_material_invalid");
        if (!File.Exists(executable))
            throw new ConnectorNoEffectException("teamcenter_visualization_runner_unavailable");
        var info = new ProcessStartInfo(executable) {
            UseShellExecute = false,
            CreateNoWindow = true,
            WorkingDirectory = Path.GetDirectoryName(executable)!,
        };
        info.ArgumentList.Add("-mime=application/x-visnetwork");
        info.ArgumentList.Add("-encodedArgs=" + EncodePath(fullPath));
        return info;
    }

    public async Task LaunchAsync(string materialPath, CancellationToken ct)
    {
        using var process = new Process { StartInfo = CreateStartInfo(materialPath) };
        try
        {
            if (!process.Start())
                throw new ConnectorNoEffectException("teamcenter_visualization_runner_start_failed");
        }
        catch (ConnectorException) { throw; }
        catch { throw new ConnectorNoEffectException("teamcenter_visualization_runner_start_failed"); }

        var exit = process.WaitForExitAsync(ct);
        var consumed = await Task.WhenAny(exit, Task.Delay(TimeSpan.FromSeconds(20), ct));
        ct.ThrowIfCancellationRequested();
        if (consumed == exit && process.ExitCode != 0)
            throw new ConnectorNoEffectException("teamcenter_visualization_runner_failed");
    }
}
