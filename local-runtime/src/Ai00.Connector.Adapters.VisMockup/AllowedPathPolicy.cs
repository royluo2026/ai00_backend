namespace Ai00.Connector.Adapters.VisMockup;

public sealed class AllowedPathPolicy
{
    private readonly string[] _roots;
    private static readonly HashSet<string> Extensions = new(StringComparer.OrdinalIgnoreCase) { ".jt", ".plmxml" };
    public AllowedPathPolicy(IEnumerable<string> roots) => _roots = roots.Select(root => Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar).ToArray();
    public string ValidateModelPath(string candidate)
    {
        var full = Path.GetFullPath(candidate);
        if (!Extensions.Contains(Path.GetExtension(full))) throw new InvalidOperationException("Only JT and PLMXML files are allowed");
        if (!_roots.Any(root => full.StartsWith(root, StringComparison.OrdinalIgnoreCase))) throw new UnauthorizedAccessException("Path is outside configured roots");
        if (!File.Exists(full)) throw new FileNotFoundException("Model file not found", full);
        return full;
    }
}
