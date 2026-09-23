using Ai00.Connector.Adapters.VisMockup;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class TeamcenterVisualizationTimingTests
{
    [Fact]
    public void All_phase_names_are_allowed_but_oversized_input_is_not()
    {
        foreach (var phase in new[] { "process_start", "login", "source_load", "launch_info", "dataset_resolve",
            "fms_init", "file_load", "fms_get_files", "material_retain", "native_consumer", "ack_final", "logout" })
            Assert.NotNull(TeamcenterProcessWorker.SanitizeVisualizationTiming(
                "AI00_TC_TIMING_V1:{\"phase\":\"" + phase + "\",\"elapsed_ms\":0}"));
        Assert.Null(TeamcenterProcessWorker.SanitizeVisualizationTiming(
            "AI00_TC_TIMING_V1:" + new string(' ', 1024) + "{\"phase\":\"login\",\"elapsed_ms\":1}"));
    }
    [Fact]
    public void Only_closed_numeric_whitelisted_timing_is_reconstructed()
    {
        Assert.Equal("AI00_TC_TIMING_V1:{\"phase\":\"login\",\"elapsed_ms\":12.5}",
            TeamcenterProcessWorker.SanitizeVisualizationTiming("AI00_TC_TIMING_V1:{ \"elapsed_ms\":12.50, \"phase\":\"login\" }"));
    }

    [Theory]
    [InlineData("password=secret")]
    [InlineData("AI00_TC_TIMING_V1:{\"phase\":\"password\",\"elapsed_ms\":1}")]
    [InlineData("AI00_TC_TIMING_V1:{\"phase\":\"login\",\"elapsed_ms\":1,\"secret\":\"ticket\"}")]
    [InlineData("AI00_TC_TIMING_V1:{\"phase\":\"login\",\"phase\":\"logout\",\"elapsed_ms\":1}")]
    [InlineData("AI00_TC_TIMING_V1:{\"phase\":\"login\",\"elapsed_ms\":\"12\"}")]
    [InlineData("AI00_TC_TIMING_V1:{\"phase\":\"login\",\"elapsed_ms\":-1}")]
    [InlineData("AI00_TC_TIMING_V1:{\"phase\":\"login\",\"elapsed_ms\":1e999}")]
    [InlineData("AI00_TC_TIMING_V1:{\"phase\":\"login\",\"elapsed_ms\":3600001}")]
    [InlineData("AI00_TC_TIMING_V1:[]")]
    [InlineData("AI00_TC_TIMING_V1:{")]
    public void Sensitive_or_malformed_diagnostics_are_not_forwarded(string line)
        => Assert.Null(TeamcenterProcessWorker.SanitizeVisualizationTiming(line));
}
