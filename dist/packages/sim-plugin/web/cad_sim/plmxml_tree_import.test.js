const test = require('node:test');
const assert = require('node:assert/strict');
const { DOMParser } = require('@xmldom/xmldom');
const { parsePlmxmlTree } = require('./plmxml_tree_import');

const xml = `<?xml version="1.0"?>
<PLMXML xmlns="http://www.plmxml.org/Schemas/PLMXMLSchema">
  <ProductDef>
    <InstanceGraph rootRefs="#pi-root">
      <ProductInstance id="pi-root" name="W10 整车"/>
      <Occurrence id="occ-root" instanceRefs="#pi-root">
        <ApplicationRef application="__TC-VIS_APP" label="#PLMXML(PS_API-doc/JT_PROP_NAME('W10/A;root\\0'))"/>
        <UserValue title="__PLM_OCC_PDM_UID" value="ROOT-UID"/>
        <UserValue title="catiaOccurrenceName" value="ROOT-CATIA"/>
      </Occurrence>
      <Occurrence id="occ-front" instanceRefs="#pi-front">
        <ApplicationRef application="__TC-VIS_APP" label="#PLMXML(PS_API-doc/JT_PROP_NAME('CHLD\\0W10/A;root\\0FRONT/B;child\\0'))"/>
        <UserValue title="__PLM_OCC_PDM_UID" value="FRONT-UID"/>
        <UserValue title="catiaOccurrenceName" value="FRONT-CATIA"/>
      </Occurrence>
    </InstanceGraph>
  </ProductDef>
</PLMXML>`;

test('manual PLMXML import projects stable occurrence identity and hierarchy', () => {
  const snapshot = parsePlmxmlTree(xml, { DOMParser });
  assert.equal(snapshot.root_node_key, 'pdm:ROOT-UID');
  assert.equal(snapshot.nodes.length, 2);
  assert.deepEqual(snapshot.nodes[0], {
    node_key: 'pdm:ROOT-UID', parent_key: null, child_order: 0,
    printable_name: 'W10 整车', occurrence_id: 'ROOT-CATIA', has_more: true,
  });
  assert.deepEqual(snapshot.nodes[1], {
    node_key: 'pdm:FRONT-UID', parent_key: 'pdm:ROOT-UID', child_order: 0,
    printable_name: 'FRONT/B;child', occurrence_id: 'FRONT-CATIA', has_more: false,
  });
  assert.equal(snapshot.source, 'manual_plmxml');
});

test('manual PLMXML import rejects incomplete shell exports', () => {
  assert.throws(() => parsePlmxmlTree('<PLMXML><InstanceGraph rootRefs="#root"/></PLMXML>', { DOMParser }),
    /plmxml_current_state_root_identity_missing/);
});

test('manual PLMXML import accepts occurrence paths expressed by instanceRefs', () => {
  const instanceRefXml = `
    <PLMXML><InstanceGraph rootRefs="inst-root">
      <ProductInstance id="inst-root" name="整车"/>
      <ProductInstance id="inst-child" name="前悬架"/>
      <Occurrence instanceRefs="#inst-root"><UserData>
        <UserValue title="__PLM_OCC_PDM_UID" value="ROOT"/>
      </UserData></Occurrence>
      <Occurrence instanceRefs="#inst-root #inst-child"><UserData>
        <UserValue title="__PLM_OCC_PDM_UID" value="CHILD"/>
        <UserValue title="catiaOccurrenceName" value="FRONT"/>
      </UserData></Occurrence>
    </InstanceGraph></PLMXML>`;
  const snapshot = parsePlmxmlTree(instanceRefXml, { DOMParser });
  assert.equal(snapshot.nodes.length, 2);
  assert.equal(snapshot.nodes[1].printable_name, '前悬架');
  assert.equal(snapshot.nodes[1].parent_key, 'pdm:ROOT');
  assert.equal(snapshot.nodes[1].occurrence_id, 'FRONT');
});
