using System.Text.Json;
using Ai00.Connector.Adapters.Mcp;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class McpAdapterPolicyTests
{
    private const string InputHash = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private const string OutputHash = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

    [Fact]
    public async Task DiscoveredToolWithoutGovernedMappingIsNotAdvertised()
    {
        var server = new FakeMcpClient([new("feishu.send_message", InputHash, OutputHash)]);
        var adapter = new McpAdapter(McpEndpointConfig.Disabled, server, []);

        var manifest = await adapter.BuildManifestAsync(default);

        Assert.Empty(manifest.Operations);
    }

    [Fact]
    public async Task SchemaDriftDisablesMappedTool()
    {
        var server = new FakeMcpClient([new("feishu.search", "sha256:" + new string('c', 64), OutputHash)]);
        var mapping = new McpToolMapping("knowledge.feishu.read@1", InputHash, "feishu.search", InputHash, OutputHash, []);
        var adapter = new McpAdapter(McpEndpointConfig.Local("stdio://feishu"), server, [mapping]);

        var health = await adapter.ProbeAsync(default);

        Assert.False(health.Ready);
        Assert.Equal("mcp_tool_contract_mismatch", health.Status);
        Assert.Empty((await adapter.BuildManifestAsync(default)).Operations);
    }

    [Fact]
    public void CloudEndpointRequiresExplicitLocalDependencyException()
    {
        var error = Assert.Throws<ConnectorException>(() => McpEndpointPolicy.RequireAllowed(
            new(new Uri("https://open.feishu.cn/mcp"), true, false, "")));
        Assert.Equal("cloud_mcp_server_preferred", error.Code);

        McpEndpointPolicy.RequireAllowed(new(
            new Uri("https://open.feishu.cn/mcp"), true, true, "Workstation-only certificate dependency; CAB-42"));
    }

    [Fact]
    public async Task ExecuteCallsOnlyPinnedMappingAndRedactsSensitiveFields()
    {
        var server = new FakeMcpClient([new("approved.search", InputHash, OutputHash)])
        {
            Result = JsonSerializer.SerializeToElement(new { title = "ok", token = "secret" }),
        };
        var mapping = new McpToolMapping("knowledge.search@1", InputHash, "approved.search", InputHash, OutputHash, ["token"]);
        var adapter = new McpAdapter(McpEndpointConfig.Local("stdio://approved"), server, [mapping]);

        var result = await adapter.ExecuteAsync(new AdapterOperation(
            "knowledge.search@1", JsonSerializer.SerializeToElement(new { query = "fixture" }), "step-1", InputHash), default);
        var output = Assert.IsType<JsonElement>(result.Data);

        Assert.Equal("ok", output.GetProperty("title").GetString());
        Assert.Equal("[REDACTED]", output.GetProperty("token").GetString());
        Assert.Equal("approved.search", server.LastCalledTool);
    }

    private sealed class FakeMcpClient(IReadOnlyList<McpToolDescriptor> tools) : IMcpClient
    {
        public JsonElement Result { get; set; } = JsonSerializer.SerializeToElement(new { });
        public string LastCalledTool { get; private set; } = "";
        public Task InitializeAsync(CancellationToken cancellationToken) => Task.CompletedTask;
        public Task<IReadOnlyList<McpToolDescriptor>> ListToolsAsync(CancellationToken cancellationToken) => Task.FromResult(tools);
        public Task<JsonElement> CallToolAsync(string toolName, JsonElement arguments, CancellationToken cancellationToken)
        {
            LastCalledTool = toolName;
            return Task.FromResult(Result);
        }
    }
}
