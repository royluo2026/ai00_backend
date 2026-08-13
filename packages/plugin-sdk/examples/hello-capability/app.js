import { Ai00PluginClient } from "./ai00-plugin-sdk.js";

const client = new Ai00PluginClient();
document.querySelector("#run").addEventListener("click", async () => {
  await client.ready();
  const output = document.querySelector("#output");
  try {
    const current = await client.storageGet("demo/run-count");
    const count = current.success ? Number(current.data?.value || 0) + 1 : 1;
    const expectedVersion = current.success ? current.data?.version : 0;
    const stored = await client.storagePut("demo/run-count", count, expectedVersion);
    if (!stored.success) throw new Error(stored.error?.message || "storage update failed");
    const versions = await client.invoke("craft.bop.version.list", {});
    output.textContent = JSON.stringify({ stored: stored.data, versions }, null, 2);
  } catch (error) {
    output.textContent = String(error);
  }
});
