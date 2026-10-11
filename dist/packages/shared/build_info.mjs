const VERSION = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;

export function formatBuildInfo({ clientType, frontendVersion, backendUrl, environment, release = null }) {
  const backendVersion = typeof release?.backendVersion === 'string' && VERSION.test(release.backendVersion)
    ? release.backendVersion : null;
  const programVersion = backendVersion && release?.frontendVersions?.[clientType] === frontendVersion &&
    typeof release?.programVersion === 'string' && VERSION.test(release.programVersion)
    ? release.programVersion : null;
  return {
    programVersion,
    text: `柔性智能业务基座 · ${programVersion ? `整体 v${programVersion}` : '整体版本未标记'} · ${environment}`,
    title: [
      `整体版本：${programVersion ? `v${programVersion}` : '未标记'}`,
      `前端版本：${VERSION.test(frontendVersion) ? `v${frontendVersion}` : '未知'}`,
      `后端版本：${backendVersion ? `v${backendVersion}` : '未标记'}`,
      `运行环境：${environment}`,
      `后端地址：${backendUrl || '本机开发代理（目标 127.0.0.1:8080）'}`,
    ].join('\n'),
  };
}
