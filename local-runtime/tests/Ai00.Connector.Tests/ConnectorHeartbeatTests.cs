using Ai00.Connector.Contracts;
using Ai00.Connector.Service;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class ConnectorHeartbeatTests
{
    [Fact]
    public async Task DedicatedReporterSendsTheExactConnectorHealthSnapshot()
    {
        var now = DateTimeOffset.Parse("2026-09-03T08:00:00Z");
        var manifest = new AdapterManifest(
            "ai00.vismockup", 1, "siemens.vismockup", "14.2.0",
            [new("vismockup.view.capture@1", "sha256:" + new string('a', 64))]);
        var expected = new ConnectorHealthReport(
            "1.0.0", [ConnectorExecutionPlan.ProtocolVersion], "user-1", "7",
            true, true, true, [manifest], now);
        var sink = new RecordingSink();
        var reporter = new ConnectorHeartbeatReporter(new FixedSource(expected), sink);

        await reporter.ReportOnceAsync(default);

        Assert.Same(expected, Assert.Single(sink.Reports));
    }

    private sealed class FixedSource(ConnectorHealthReport report) : IConnectorHealthSource
    {
        public ConnectorHealthReport Read() => report;
    }

    private sealed class RecordingSink : IConnectorHeartbeatSink
    {
        public List<ConnectorHealthReport> Reports { get; } = [];
        public Task SendAsync(ConnectorHealthReport report, CancellationToken cancellationToken)
        {
            Reports.Add(report);
            return Task.CompletedTask;
        }
    }
}
