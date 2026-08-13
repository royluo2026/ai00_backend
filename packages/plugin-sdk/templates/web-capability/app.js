import { Ai00PluginClient } from "./ai00-plugin-sdk.js";

const client = new Ai00PluginClient();
const counterKey = "demo/invocation-count";
const status = document.querySelector("#status");
const capabilities = document.querySelector("#capabilities");
const count = document.querySelector("#count");
const output = document.querySelector("#output");
const runButton = document.querySelector("#run");
const resetButton = document.querySelector("#reset");

function requireSuccess(result, operation) {
  if (!result?.success) throw new Error(result?.error?.message || `${operation}失败`);
  return result.data;
}

async function readCounter() {
  const result = await client.storageGet(counterKey);
  if (!result.success) return { value: 0, version: 0 };
  return { value: Number(result.data?.value || 0), version: Number(result.data?.version || 0) };
}

async function refreshCounter() {
  const current = await readCounter();
  count.textContent = String(current.value);
  return current;
}

async function initialize() {
  try {
    const granted = await client.ready();
    capabilities.replaceChildren(...granted.map((item) => {
      const chip = document.createElement("span");
      chip.textContent = item;
      return chip;
    }));
    await refreshCounter();
    status.textContent = "已连接；所有调用将由宿主再次鉴权并自动计入使用量。";
    runButton.disabled = false;
    resetButton.disabled = false;
  } catch (error) {
    status.textContent = `初始化失败：${error instanceof Error ? error.message : String(error)}`;
  }
}

runButton.addEventListener("click", async () => {
  runButton.disabled = true;
  output.textContent = "调用中…";
  try {
    const current = await readCounter();
    const stored = requireSuccess(
      await client.storagePut(counterKey, current.value + 1, current.version),
      "保存计数",
    );
    const versions = requireSuccess(
      await client.invoke("craft.bop.version.list", {}),
      "调用 craft.bop.version.list",
    );
    count.textContent = String(current.value + 1);
    output.textContent = JSON.stringify({ stored, versions }, null, 2);
  } catch (error) {
    output.textContent = `失败：${error instanceof Error ? error.message : String(error)}`;
  } finally {
    runButton.disabled = false;
  }
});

resetButton.addEventListener("click", async () => {
  resetButton.disabled = true;
  try {
    const current = await readCounter();
    if (current.version > 0) requireSuccess(await client.storageDelete(counterKey, current.version), "删除计数");
    await refreshCounter();
    output.textContent = "示例计数已清空";
  } catch (error) {
    output.textContent = `失败：${error instanceof Error ? error.message : String(error)}`;
  } finally {
    resetButton.disabled = false;
  }
});

initialize();
