using System.Security.Cryptography;
using System.Text.Json;
using System.Xml;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

internal sealed record VisMockupPlmxmlNode(
    string StableOccurrenceKey,
    string? ParentStableOccurrenceKey,
    int ChildOrder,
    int Depth,
    string PrintableName,
    string ProductRef,
    string RevisionCode,
    string PdmOccurrenceUid,
    string AbsoluteOccurrenceUid,
    IReadOnlyList<string> CloneStableChain,
    IReadOnlyList<string> OccurrencePath,
    string CatiaOccurrenceName);

internal sealed record VisMockupPlmxmlProjection(
    string RootStableOccurrenceKey,
    IReadOnlyList<VisMockupPlmxmlNode> Nodes,
    string SnapshotHash);

internal sealed class VisMockupPlmxmlProjectionReader
{
    public VisMockupPlmxmlProjection Read(Stream stream, int maxNodes)
    {
        if (maxNodes < 1) throw new ConnectorException("bom_snapshot_limit_invalid");
        var settings = new XmlReaderSettings
        {
            DtdProcessing = DtdProcessing.Prohibit,
            XmlResolver = null,
            IgnoreComments = true,
            MaxCharactersInDocument = 64L * 1024 * 1024,
        };
        using var reader = XmlReader.Create(stream, settings);
        var rootInstanceId = "";
        var rootName = "";
        var productNames = new Dictionary<string, string>(StringComparer.Ordinal);
        Occurrence? current = null;
        var occurrences = new List<Occurrence>();
        var occurrenceOrdinal = 0;
        while (reader.Read())
        {
            if (reader.NodeType == XmlNodeType.Element)
            {
                if (reader.LocalName == "InstanceGraph")
                    rootInstanceId = References(reader.GetAttribute("rootRefs")).FirstOrDefault() ?? "";
                else if (reader.LocalName == "ProductInstance")
                {
                    var id = reader.GetAttribute("id") ?? "";
                    var name = reader.GetAttribute("name") ?? "";
                    if (id.Length > 0) productNames[id] = name;
                    if (id == rootInstanceId) rootName = name;
                }
                else if (reader.LocalName == "Occurrence")
                {
                    current = new(
                        reader.GetAttribute("id") ?? "",
                        occurrenceOrdinal++,
                        References(reader.GetAttribute("instanceRefs")),
                        new(StringComparer.Ordinal),
                        new(StringComparer.Ordinal));
                    occurrences.Add(current);
                }
                else if (reader.LocalName == "ApplicationRef" && current is not null)
                    current.ApplicationRefs[reader.GetAttribute("application") ?? ""] = reader.GetAttribute("label") ?? "";
                else if (reader.LocalName == "UserValue" && current is not null)
                    current.UserValues[reader.GetAttribute("title") ?? ""] = reader.GetAttribute("value") ?? "";
            }
            else if (reader.NodeType == XmlNodeType.EndElement && reader.LocalName == "Occurrence")
                current = null;
        }

        var rootOccurrence = occurrences.SingleOrDefault(value => value.InstanceRefs.Count == 1 && value.InstanceRefs[0] == rootInstanceId)
            ?? throw new ConnectorException("plmxml_current_state_root_identity_missing");
        var rootPdmUid = Value(rootOccurrence, "__PLM_OCC_PDM_UID");
        if (string.IsNullOrWhiteSpace(rootPdmUid))
            throw new ConnectorException("plmxml_current_state_root_identity_missing");
        var paths = occurrences
            .Select(value => new PathEntry(
                CurrentStatePath(value.ApplicationRefs.GetValueOrDefault("__TC-VIS_APP", "")), value, null))
            .Where(value => value.Path.Count > 0)
            .OrderBy(value => value.Path.Count)
            .ThenBy(value => value.Occurrence.Ordinal)
            .ToArray();
        if (paths.Length == 0)
            paths = occurrences
                .Where(value => value.InstanceRefs.Count > 0 && value.InstanceRefs[0] == rootInstanceId &&
                    !string.IsNullOrWhiteSpace(Value(value, "__PLM_OCC_PDM_UID")))
                .Select(value => new PathEntry(value.InstanceRefs, value,
                    productNames.GetValueOrDefault(value.InstanceRefs[^1], value.InstanceRefs[^1])))
                .OrderBy(value => value.Path.Count)
                .ThenBy(value => value.Occurrence.Ordinal)
                .ToArray();
        if (paths.Length == 0) throw new ConnectorException("plmxml_current_state_structure_missing");

        var rootPath = paths[0].Path[0];
        var rootKey = StableKey(rootPdmUid);
        var rootProduct = ItemRevision(rootPath);
        var nodes = new List<VisMockupPlmxmlNode>
        {
            new(rootKey, null, 0, 0, string.IsNullOrWhiteSpace(rootName) ? rootPath : rootName,
                rootProduct.Item, rootProduct.Revision, rootPdmUid,
                Value(rootOccurrence, "__PLM_ABSOCC_UID"), [], [rootPath],
                Value(rootOccurrence, "catiaOccurrenceName")),
        };
        var keyByPath = new Dictionary<string, string>(StringComparer.Ordinal) { [PathKey([rootPath])] = rootKey };
        var pdmUids = new HashSet<string>(StringComparer.Ordinal) { rootPdmUid };
        var childOrders = new Dictionary<string, int>(StringComparer.Ordinal);
        foreach (var entry in paths)
        {
            if (entry.Path.Count == 1) continue;
            if (nodes.Count >= maxNodes) throw new ConnectorException("bom_snapshot_limit_exceeded");
            var pdmUid = Value(entry.Occurrence, "__PLM_OCC_PDM_UID");
            if (string.IsNullOrWhiteSpace(pdmUid) || !pdmUids.Add(pdmUid))
                throw new ConnectorException("plmxml_current_state_identity_ambiguous");
            var pathKey = PathKey(entry.Path);
            if (keyByPath.ContainsKey(pathKey))
                throw new ConnectorException("plmxml_current_state_identity_ambiguous");
            var parentPath = entry.Path.Take(entry.Path.Count - 1).ToArray();
            if (!keyByPath.TryGetValue(PathKey(parentPath), out var parentKey))
                throw new ConnectorException("plmxml_current_state_parent_missing");
            var printableName = entry.PrintableName ?? entry.Path[^1];
            var product = ItemRevision(printableName);
            var order = childOrders.GetValueOrDefault(parentKey);
            childOrders[parentKey] = order + 1;
            var key = StableKey(pdmUid);
            nodes.Add(new(
                key, parentKey, order, entry.Path.Count - 1, printableName,
                product.Item, product.Revision, pdmUid,
                Value(entry.Occurrence, "__PLM_ABSOCC_UID"),
                CloneStableChain(entry.Occurrence.ApplicationRefs.GetValueOrDefault("__TC-VIS_NGID", "")),
                entry.Path.Select(value => productNames.GetValueOrDefault(value, value)).ToArray(),
                Value(entry.Occurrence, "catiaOccurrenceName")));
            keyByPath[pathKey] = key;
        }
        var canonical = JsonSerializer.SerializeToUtf8Bytes(nodes);
        var hash = "sha256:" + Convert.ToHexString(SHA256.HashData(canonical)).ToLowerInvariant();
        return new(rootKey, nodes, hash);
    }

    private static IReadOnlyList<string> References(string? value) =>
        (value ?? "").Split(' ', StringSplitOptions.RemoveEmptyEntries).Select(item => item.TrimStart('#')).ToArray();

    private static string Value(Occurrence occurrence, string key) => occurrence.UserValues.GetValueOrDefault(key, "");
    private static string StableKey(string pdmUid) => "pdm:" + pdmUid;
    private static string PathKey(IEnumerable<string> path) => string.Join('\u001f', path);

    private static IReadOnlyList<string> CurrentStatePath(string label)
    {
        var payload = Payload(label, "JT_PROP_NAME");
        var values = payload.Split("\\0", StringSplitOptions.RemoveEmptyEntries);
        return values.Length > 0 && values[0].StartsWith("CHLD", StringComparison.Ordinal)
            ? values.Skip(1).ToArray() : values;
    }

    private static IReadOnlyList<string> CloneStableChain(string label)
    {
        const string marker = "$$NGID<chain>=\"__PLM_CLONE_STABLE_INST_UID\"";
        var values = Payload(label, "NGID").Split("\\0", StringSplitOptions.None);
        var start = Array.IndexOf(values, marker);
        if (start < 0) return [];
        return values.Skip(start + 1).TakeWhile(value => !value.StartsWith("$$NGID<", StringComparison.Ordinal))
            .Where(value => value.Length > 0).ToArray();
    }

    private static string Payload(string label, string function)
    {
        var prefix = $"#PLMXML(PS_API-doc/{function}('";
        const string suffix = "'))";
        return label.StartsWith(prefix, StringComparison.Ordinal) && label.EndsWith(suffix, StringComparison.Ordinal)
            ? label[prefix.Length..^suffix.Length] : "";
    }

    private static (string Item, string Revision) ItemRevision(string path)
    {
        var slash = path.IndexOf('/');
        var semicolon = path.IndexOf(';', slash + 1);
        return slash > 0 && semicolon > slash
            ? (path[..slash], path[(slash + 1)..semicolon]) : ("", "");
    }

    private sealed class Occurrence(
        string id,
        int ordinal,
        IReadOnlyList<string> instanceRefs,
        Dictionary<string, string> applicationRefs,
        Dictionary<string, string> userValues)
    {
        public string Id { get; } = id;
        public int Ordinal { get; } = ordinal;
        public IReadOnlyList<string> InstanceRefs { get; } = instanceRefs;
        public Dictionary<string, string> ApplicationRefs { get; } = applicationRefs;
        public Dictionary<string, string> UserValues { get; } = userValues;
    }

    private sealed record PathEntry(
        IReadOnlyList<string> Path,
        Occurrence Occurrence,
        string? PrintableName);
}
