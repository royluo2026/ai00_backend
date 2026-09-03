using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.Mcp;

public sealed record McpToolMapping(
    string OperationId,
    string ContractHash,
    string ToolName,
    string InputSchemaHash,
    string OutputSchemaHash,
    IReadOnlyList<string> SensitiveFields);

public sealed record McpToolDescriptor(string Name, string InputSchemaHash, string OutputSchemaHash);

public sealed record McpEndpointConfig(
    Uri Endpoint,
    bool Enabled,
    bool LocalDependencyRequired,
    string AuditReason)
{
    public static McpEndpointConfig Disabled { get; } = new(new Uri("stdio://disabled"), false, false, "");
    public static McpEndpointConfig Local(string endpoint) => new(new Uri(endpoint), true, false, "");
}

public static class McpEndpointPolicy
{
    public static void RequireAllowed(McpEndpointConfig config)
    {
        if (!config.Enabled) return;
        if (config.Endpoint.Scheme == Uri.UriSchemeHttps &&
            (!config.LocalDependencyRequired || string.IsNullOrWhiteSpace(config.AuditReason)))
            throw new ConnectorException("cloud_mcp_server_preferred");
        if (config.Endpoint.Scheme is not ("stdio" or "pipe" or "http" or "https"))
            throw new ConnectorException("mcp_transport_not_allowed");
        if (config.Endpoint.Scheme == Uri.UriSchemeHttp && !config.Endpoint.IsLoopback && !IsPrivateHost(config.Endpoint.Host))
            throw new ConnectorException("mcp_endpoint_not_local_or_intranet");
    }

    private static bool IsPrivateHost(string host) =>
        host.Equals("localhost", StringComparison.OrdinalIgnoreCase) ||
        host.StartsWith("10.", StringComparison.Ordinal) ||
        host.StartsWith("192.168.", StringComparison.Ordinal) ||
        (host.StartsWith("172.", StringComparison.Ordinal) && int.TryParse(host.Split('.').ElementAtOrDefault(1), out var part) && part is >= 16 and <= 31);
}
