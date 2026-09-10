using Ai00.Connector.Adapters.VisMockup;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupTreeFingerprintTests
{
    [Fact]
    public void SameSourceAndTreeProduceTheSameHashesAcrossSessions()
    {
        var root = new FakeNode("root", "W10", "root-occ", "root-model", []);
        var left = new FakeDocument("session-a", @"C:\Models\W10.vfz", root);
        var right = new FakeDocument("session-b", @"c:\models\W10.vfz", root);

        var leftManifest = VisMockupTreeFingerprint.Create(left);
        var rightManifest = VisMockupTreeFingerprint.Create(right);

        Assert.Equal(leftManifest.DocumentIdentityHash, rightManifest.DocumentIdentityHash);
        Assert.Equal(leftManifest.RootSubtreeHash, rightManifest.RootSubtreeHash);
    }

    [Fact]
    public void ChangedChildModelChangesOnlyTheChildAndItsAncestorChain()
    {
        var before = DocumentWithParts("part-2-model-a", ["part-1", "part-2"]);
        var after = DocumentWithParts("part-2-model-b", ["part-1", "part-2"]);

        var beforeManifest = VisMockupTreeFingerprint.Create(before);
        var afterManifest = VisMockupTreeFingerprint.Create(after);

        Assert.Equal(
            beforeManifest.Node("part-1").SubtreeHash,
            afterManifest.Node("part-1").SubtreeHash);
        Assert.NotEqual(
            beforeManifest.Node("part-2").RevisionFingerprint,
            afterManifest.Node("part-2").RevisionFingerprint);
        Assert.NotEqual(beforeManifest.RootSubtreeHash, afterManifest.RootSubtreeHash);
    }

    [Fact]
    public void ChildReorderChangesTheParentButNotTheChildren()
    {
        var before = DocumentWithParts("part-2-model", ["part-1", "part-2"]);
        var after = DocumentWithParts("part-2-model", ["part-2", "part-1"]);

        var beforeManifest = VisMockupTreeFingerprint.Create(before);
        var afterManifest = VisMockupTreeFingerprint.Create(after);

        Assert.Equal(beforeManifest.Node("part-1").SubtreeHash, afterManifest.Node("part-1").SubtreeHash);
        Assert.Equal(beforeManifest.Node("part-2").SubtreeHash, afterManifest.Node("part-2").SubtreeHash);
        Assert.NotEqual(beforeManifest.RootSubtreeHash, afterManifest.RootSubtreeHash);
    }

    [Fact]
    public void MissingExternalRevisionEvidenceIsUncertainNotFresh()
    {
        var document = new FakeDocument(
            "session-a", "tc://bom/W10", new FakeNode("root", "W10", "root-occ", "root-model", []));

        var manifest = VisMockupTreeFingerprint.Create(document);

        Assert.Equal(CacheFreshness.Uncertain, manifest.Freshness);
    }

    [Fact]
    public void ExistingLocalSourceProvidesAStableExternalRevisionFingerprint()
    {
        var directory = Path.Combine(Path.GetTempPath(), "ai00-vm-fingerprint-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, "W10.vfz");
        File.WriteAllText(path, "model");
        try
        {
            var document = new FakeDocument(
                "session-a", path, new FakeNode("root", "W10", "root-occ", "root-model", []));

            var manifest = VisMockupTreeFingerprint.Create(document);

            Assert.Equal(CacheFreshness.Fresh, manifest.Freshness);
            Assert.StartsWith("sha256:", manifest.ExternalRevisionFingerprint);
        }
        finally
        {
            Directory.Delete(directory, true);
        }
    }

    private static FakeDocument DocumentWithParts(string secondModel, string[] order)
    {
        var parts = new Dictionary<string, IVisMockupNode>(StringComparer.Ordinal)
        {
            ["part-1"] = new FakeNode("part-1", "Part 1", "occ-1", "part-1-model", []),
            ["part-2"] = new FakeNode("part-2", "Part 2", "occ-2", secondModel, []),
        };
        var root = new FakeNode("root", "W10", "root-occ", "root-model", order.Select(key => parts[key]).ToArray());
        return new FakeDocument("session", "tc://bom/W10", root);
    }
}
