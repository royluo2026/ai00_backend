/**
 * 飞书独立域核心脚本
 * 功能：主题同步、登录管理、iframe内嵌、跨域处理
 */
document.addEventListener('DOMContentLoaded', async () => {
  // ===================== 全局配置 =====================
  const STORAGE_KEY = "feishu_login_data";
  const root = document.documentElement;
  let feishuConfig = null;

  // ===================== 1. 初始化：同步全局主题 =====================
  const initTheme = async () => {
    const saved = localStorage.getItem("appTheme") || "light";
    root.setAttribute("data-theme", saved);
  };

  // ===================== 2. 获取飞书配置 =====================
  const getFeishuConfig = async () => {
    if (feishuConfig) return feishuConfig;
    const cf = window._cloudFetch || window.parent?._cloudFetch;
    if (cf) {
      try {
        const res = await cf('/api/feishu/config');
        feishuConfig = res?.data || res || {};
      } catch { feishuConfig = {}; }
    } else {
      feishuConfig = {};
    }
    return feishuConfig;
  };

  // ===================== 3. 登录状态管理 =====================
  const saveLoginStatus = (token) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ token, time: Date.now() }));
  };

  const checkLoginStatus = () => {
    const data = localStorage.getItem(STORAGE_KEY);
    if (!data) return false;
    try {
      const { token, time } = JSON.parse(data);
      // 7天自动过期
      return Date.now() - time < 7 * 24 * 3600 * 1000 && token;
    } catch (e) {
      return false;
    }
  };

  const logout = async () => {
    localStorage.removeItem(STORAGE_KEY);
    window.location.href = "login.html";
  };

  // ===================== 4. 登录页逻辑 =====================
  const initLoginPage = async () => {
    const loginBtn = document.getElementById("loginBtn");
    const statusText = document.getElementById("statusText");
    const config = await getFeishuConfig();

    // 自动检查登录态
    if (checkLoginStatus()) {
      statusText.textContent = "已登录，正在跳转...";
      setTimeout(() => window.location.href = "chat_doc.html", 1000);
      return;
    }

    // 模拟飞书扫码登录
    loginBtn.addEventListener("click", async () => {
      loginBtn.disabled = true;
      loginBtn.textContent = "正在登录...";
      statusText.textContent = "扫码授权中，请稍候...";

      // 模拟登录成功（正式环境替换为飞书OAuth回调）
      setTimeout(() => {
        const mockToken = "feishu_token_" + Date.now();
        saveLoginStatus(mockToken);
        statusText.textContent = "登录成功，跳转中...";
        window.location.href = config.redirect_uri;
      }, 2000);
    });
  };

  // ===================== 5. 聊天/文档内嵌页逻辑 =====================
  const initChatDocPage = async () => {
    // 登录校验
    if (!checkLoginStatus()) {
      window.location.href = "login.html";
      return;
    }

    const config = await getFeishuConfig();
    const chatIframe = document.getElementById("chatIframe");
    const docIframe = document.getElementById("docIframe");
    const logoutBtn = document.getElementById("logoutBtn");

    // 绑定登出
    logoutBtn.addEventListener("click", logout);

    // 加载飞书内嵌页面（处理跨域）
    chatIframe.src = config.chat_url;
    docIframe.src = config.doc_url;

    // 加载完成监听
    chatIframe.onload = () => console.log("✅ 飞书聊天加载完成");
    docIframe.onload = () => console.log("✅ 飞书文档加载完成");
  };

  // ===================== 页面自动识别初始化 =====================
  const initPage = async () => {
    await initTheme();
    const isLoginPage = window.location.pathname.includes("login.html");
    
    if (isLoginPage) {
      initLoginPage();
    } else {
      initChatDocPage();
    }
  };

  // 启动
  initPage();
});