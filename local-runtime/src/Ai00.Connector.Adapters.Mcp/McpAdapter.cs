using System.Text.Json;
using System.Text.Json.Nodes;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.Mcp;

public interface IMcpClient
{
    Task InitializeAsync(CancellationToken cancellationToken);
    Task<IReadOnlyList<McpToolDescriptor>> ListToolsAsync(CancellationToken cancellationToken);
    Task<JsonElement> CallToolAsync(string toolName, JsonElement arguments, CancellationToken cancellationToken);
}

public sealed class McpAdapter : IConnectorAdapter
{
    private readonly McpEndpointConfig _config;
    private readonly IMcpClient _client;
    private readonly IReadOnlyDictionary<string, McpToolMapping> _mappings;
    private AdapterManifest _manifest = EmptyManifest();

    public McpAdapter(McpEndpointConfig config, IMcpClient client, IEnumerable<McpToolMapping> mappings)
    {
        McpEndpointPolicy.RequireAllowed(config);
        _config = config;
        _client = client;
        _mappings = mappings.ToDictionary(item => item.OperationId, StringComparer.Ordinal);
    }

    public AdapterManifest Manifest => _manifest;

    public async Task<AdapterManifest> BuildManifestAsync(CancellationToken cancellationToken)
    {
        if (!_config.Enabled) return _manifest = EmptyManifest();
        var tools = await DiscoverAsync(cancellationToken);
        var operations = _mappings.Values
            .Where(mapping => tools.TryGetValue(mapping.ToolName, out var tool) && Matches(mapping, tool))
            .Select(mapping => new AdapterOperationContract(mapping.OperationId, mapping.ContractHash))
            .OrderBy(item => item.OperationId, StringComparer.Ordinal)
            .ToArray();
        return _manifest = new("ai00.mcp", 1, "mcp-server", "1.0.0", operations);
    }

    public async Task<AdapterHealth> ProbeAsync(CancellationToken cancellationToken)
    {
        if (!_config.Enabled) return new(false, "mcp_disabled");
        try
        {
            var tools = await DiscoverAsync(cancellationToken);
            if (_mappings.Values.Any(mapping => !tools.TryGetValue(mapping.ToolName, out var tool) || !Matches(mapping, tool)))
            {
                _manifest = EmptyManifest();
                return new(false, "mcp_tool_contract_mismatch");
            }
            await BuildManifestAsync(cancellationToken);
            return new(true, "ready", true, true, "1.0.0");
        }
        catch (ConnectorException exception)
        {
            _manifest = EmptyManifest();
            return new(false, exception.Code);
        }
    }

    public async Task<AdapterResult> ExecuteAsync(AdapterOperation operation, CancellationToken cancellationToken)
    {
        if (!_config.Enabled) throw new ConnectorException("mcp_disabled");
        if (!_mappings.TryGetValue(operation.OperationId, out var mapping) ||
            !string.Equals(mapping.ContractHash, operation.ContractHash, StringComparison.Ordinal))
            throw new ConnectorException("adapter_operation_not_allowed");
        var tools = await DiscoverAsync(cancellationToken);
        if (!tools.TryGetValue(mapping.ToolName, out var tool) || !Matches(mapping, tool))
            throw new ConnectorException("mcp_tool_contract_mismatch");
        var result = await _client.CallToolAsync(mapping.ToolName, operation.Payload, cancellationToken);
        return new(true, Redact(result, mapping.SensitiveFields));
    }

    private async Task<IReadOnlyDictionary<string, McpToolDescriptor>> DiscoverAsync(CancellationToken cancellationToken)
    {
        await _client.InitializeAsync(cancellationToken);
        var tools = await _client.ListToolsAsync(cancellationToken);
        return tools.ToDictionary(item => item.Name, StringComparer.Ordinal);
    }

    private static bool Matches(McpToolMapping mapping, McpToolDescriptor tool) =>
        string.Equals(mapping.InputSchemaHash, tool.InputSchemaHash, StringComparison.Ordinal) &&
        string.Equals(mapping.OutputSchemaHash, tool.OutputSchemaHash, StringComparison.Ordinal);

    private static JsonElement Redact(JsonElement value, IReadOnlyList<string> sensitiveFields)
    {
        if (value.ValueKind != JsonValueKind.Object || sensitiveFields.Count == 0) return value.Clone();
        var node = JsonNode.Parse(value.GetRawText())!.AsObject();
        foreach (var field in sensitiveFields)
            if (node.ContainsKey(field)) node[field] = "[REDACTED]";
        return JsonSerializer.SerializeToElement(node);
    }

    private static AdapterManifest EmptyManifest() => new("ai00.mcp", 1, "mcp-server", "1.0.0", []);
}

public sealed class JsonRpcStdioMcpClient(TextReader input, TextWriter output) : IMcpClient
{
    private int _nextId;

    public async Task InitializeAsync(CancellationToken cancellationToken) =>
        _ = await RequestAsync("initialize", new { protocolVersion = "2025-06-18", capabilities = new { }, clientInfo = new { name = "ai00-connector", version = "1.0.0" } }, cancellationToken);

    public async Task<IReadOnlyList<McpToolDescriptor>> ListToolsAsync(CancellationToken cancellationToken)
    {
        var result = await RequestAsync("tools/list", new { }, cancellationToken);
        return result.GetProperty("tools").EnumerateArray().Select(tool => new McpToolDescriptor(
            tool.GetProperty("name").GetString() ?? throw new ConnectorException("mcp_tool_invalid"),
            tool.GetProperty("inputSchemaHash").GetString() ?? throw new ConnectorException("mcp_tool_schema_hash_missing"),
            tool.GetProperty("outputSchemaHash").GetString() ?? throw new ConnectorException("mcp_tool_schema_hash_missing"))).ToArray();
    }

    public Task<JsonElement> CallToolAsync(string toolName, JsonElement arguments, CancellationToken cancellationToken) =>
        RequestAsync("tools/call", new { name = toolName, arguments }, cancellationToken);

    private async Task<JsonElement> RequestAsync(string method, object parameters, CancellationToken cancellationToken)
    {
        var id = Interlocked.Increment(ref _nextId);
        await output.WriteLineAsync(JsonSerializer.Serialize(new { jsonrpc = "2.0", id, method, @params = parameters }));
        await output.FlushAsync(cancellationToken);
        var line = await input.ReadLineAsync(cancellationToken) ?? throw new ConnectorException("mcp_connection_closed");
        using var response = JsonDocument.Parse(line);
        if (!response.RootElement.TryGetProperty("id", out var responseId) || responseId.GetInt32() != id)
            throw new ConnectorException("mcp_response_mismatch");
        if (response.RootElement.TryGetProperty("error", out _)) throw new ConnectorException("mcp_tool_failed");
        return response.RootElement.GetProperty("result").Clone();
    }
}
