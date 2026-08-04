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
    const echoed = await client.invoke("system.echo", { message: "hello from isolated plugin", runCount: count });
    output.textContent = JSON.stringify({ stored: stored.data, echoed }, null, 2);
  } catch (error) {
    output.textContent = String(error);
  }
});