'use strict';

const assert = require('assert');
const { createExistingCapabilityClient } = require('./existing_capability_client.js');

async function runExistingCapabilityClientTests() {
  const client = createExistingCapabilityClient(async () => ({
    success: true,
    data: {
      ok: true,
      data: {
        profile: {
          actor_gid: 'user-1',
          display_name: 'Tester',
          tenant_gid: 'tenant-1',
          team_gids: [],
          locale: 'zh-CN',
          timezone: 'Asia/Shanghai',
          permission_ids: [],
        },
      },
    },
  }));

  const profile = await client.call('base.identity.session.profile.get');
  assert.strictEqual(profile.actor_gid, 'user-1', 'identity adapter must expose the authenticated actor');
  assert.strictEqual(profile.display_name, 'Tester');
}

if (require.main === module) {
  runExistingCapabilityClientTests()
    .then(() => console.log('existing_capability_client: all tests passed'))
    .catch(error => {
      console.error(error);
      process.exitCode = 1;
    });
}

module.exports = { runExistingCapabilityClientTests };
