using System.Reflection;
using Ai00.Connector.Adapters.VisMockup;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupMetadataTests
{
    [Fact]
    public void Native_occurrence_metadata_uses_the_required_output_parameter()
    {
        var native = new NativeNode();
        var type = typeof(WindowsVisMockupCom).GetNestedType("DynamicNode", BindingFlags.NonPublic)!;
        var node = (IVisMockupNode)Activator.CreateInstance(type, native)!;

        Assert.Equal("tc-occurrence", node.OccurrenceId);
        Assert.Contains("tc-occurrence", node.OccurrenceIds);
        Assert.Equal("part-id", node.ModelId);
        Assert.Equal(1, native.MetaDataProperties.OccurrenceReads);
    }

    public sealed class NativeNode
    {
        public NativeMetadata MetaDataProperties { get; } = new();
    }

    // VisAutomation.tlb: void GetPropertyByName(BSTR name, [out] VARIANT* value).
    // A one-argument fake would conceal the native interop regression.
    public sealed class NativeMetadata
    {
        public int OccurrenceReads { get; private set; }
        public void GetPropertyByName(string name, out object value)
        {
            if (name == "bl_occurrence_uid") OccurrenceReads++;
            value = name switch
            {
                "bl_occurrence_uid" => "tc-occurrence",
                "itemId" => "part-id",
                _ => "",
            };
        }
    }
}
