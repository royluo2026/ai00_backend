using System.Text;
using Ai00.Connector.Adapters.VisMockup;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupPlmxmlProjectionReaderTests
{
    [Fact]
    public void CurrentStateOccurrencesBecomeACompleteStableTree()
    {
        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(CurrentStateXml));

        var projection = new VisMockupPlmxmlProjectionReader().Read(stream, maxNodes: 100);

        Assert.Equal(3, projection.Nodes.Count);
        var root = projection.Nodes[0];
        var assembly = projection.Nodes[1];
        var part = projection.Nodes[2];
        Assert.Equal(root.StableOccurrenceKey, assembly.ParentStableOccurrenceKey);
        Assert.Equal(assembly.StableOccurrenceKey, part.ParentStableOccurrenceKey);
        Assert.Equal("PART-2", part.ProductRef);
        Assert.Equal("B", part.RevisionCode);
        Assert.Equal("pdm-part", part.PdmOccurrenceUid);
        Assert.Equal("abs-part", part.AbsoluteOccurrenceUid);
        Assert.Equal(["clone-root", "clone-assembly", "clone-part"], part.CloneStableChain);
        Assert.Equal([RootPath, AssemblyPath, PartPath], part.OccurrencePath);
        Assert.Equal("part-occ", part.CatiaOccurrenceName);
        Assert.StartsWith("sha256:", projection.SnapshotHash);
    }

    [Fact]
    public void InstanceReferenceChainsBecomeACompleteStableTree()
    {
        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(InstanceReferenceXml));

        var projection = new VisMockupPlmxmlProjectionReader().Read(stream, maxNodes: 100);

        Assert.Equal(2, projection.Nodes.Count);
        Assert.Equal("pdm:root-pdm", projection.RootStableOccurrenceKey);
        Assert.Equal("Root", projection.Nodes[0].PrintableName);
        Assert.Equal("Child", projection.Nodes[1].PrintableName);
        Assert.Equal("pdm:root-pdm", projection.Nodes[1].ParentStableOccurrenceKey);
        Assert.Equal("child-catia", projection.Nodes[1].CatiaOccurrenceName);
    }

    private const string RootPath = "ROOT/00;1-Root.asm;-1;0:";
    private const string AssemblyPath = "ASSY-1/A;1-Assembly.asm;-1;10:";
    private const string PartPath = "PART-2/B;1-Part.prt;-1;20:";
    private const string CurrentStateXml = """
        <?xml version="1.0" encoding="utf-8"?>
        <PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema" schemaVersion="6" author="test">
          <ProductDef id="product"><InstanceGraph id="graph" rootRefs="inst-root">
            <ProductInstance id="inst-root" name="ROOT/00;1-Root" partRef="#view-root" />
            <ProductRevisionView id="view-root" name="ROOT/00;1-Root">
              <UserData><UserValue title="__PLM_ITEM_ID" value="ROOT"/><UserValue title="__PLM_REVISION_ID" value="00"/></UserData>
            </ProductRevisionView>
          </InstanceGraph></ProductDef>
          <Occurrence id="root-occ" instanceRefs="#inst-root"><UserData>
            <UserValue title="__PLM_OCC_PDM_UID" value="pdm-root"/>
            <UserValue title="__PLM_ABSOCC_UID" value="abs-root"/>
          </UserData></Occurrence>
          <Occurrence id="occ-assembly">
            <ApplicationRef application="__TC-VIS_APP" label="#PLMXML(PS_API-doc/JT_PROP_NAME('CHLD0000\0ROOT/00;1-Root.asm;-1;0:\0ASSY-1/A;1-Assembly.asm;-1;10:\0\0'))"/>
            <ApplicationRef application="__TC-VIS_NGID" label="#PLMXML(PS_API-doc/NGID('$$NGID&lt;chain&gt;=&quot;__PLM_CLONE_STABLE_INST_UID&quot;\0clone-root\0clone-assembly\0$$NGID&lt;chain&gt;=&quot;JT_PROP_NAME&quot;\0ignored\0'))"/>
            <UserData><UserValue title="__PLM_OCC_PDM_UID" value="pdm-assembly"/><UserValue title="__PLM_ABSOCC_UID" value="abs-assembly"/><UserValue title="catiaOccurrenceName" value="assembly-occ"/></UserData>
          </Occurrence>
          <Occurrence id="occ-part">
            <ApplicationRef application="__TC-VIS_APP" label="#PLMXML(PS_API-doc/JT_PROP_NAME('CHLD0000\0ROOT/00;1-Root.asm;-1;0:\0ASSY-1/A;1-Assembly.asm;-1;10:\0PART-2/B;1-Part.prt;-1;20:\0\0'))"/>
            <ApplicationRef application="__TC-VIS_NGID" label="#PLMXML(PS_API-doc/NGID('$$NGID&lt;chain&gt;=&quot;__PLM_CLONE_STABLE_INST_UID&quot;\0clone-root\0clone-assembly\0clone-part\0$$NGID&lt;chain&gt;=&quot;JT_PROP_NAME&quot;\0ignored\0'))"/>
            <UserData><UserValue title="__PLM_OCC_PDM_UID" value="pdm-part"/><UserValue title="__PLM_ABSOCC_UID" value="abs-part"/><UserValue title="catiaOccurrenceName" value="part-occ"/></UserData>
          </Occurrence>
        </PLMXML>
        """;

    private const string InstanceReferenceXml = """
        <?xml version="1.0" encoding="utf-8"?>
        <PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema">
          <InstanceGraph rootRefs="inst-root">
            <ProductInstance id="inst-root" name="Root"/>
            <ProductInstance id="inst-child" name="Child"/>
            <Occurrence instanceRefs="#inst-root"><UserData>
              <UserValue title="__PLM_OCC_PDM_UID" value="root-pdm"/>
            </UserData></Occurrence>
            <Occurrence instanceRefs="#inst-root #inst-child"><UserData>
              <UserValue title="__PLM_OCC_PDM_UID" value="child-pdm"/>
              <UserValue title="catiaOccurrenceName" value="child-catia"/>
            </UserData></Occurrence>
          </InstanceGraph>
        </PLMXML>
        """;
}
