/* ======================================
   工艺画布 - 多人协同核心逻辑
   低延迟、轻量、实时渲染
 ====================================== */
window.CollabUI = {
    memberList: document.getElementById('memberList'),
    memberCount: document.getElementById('memberCount'),
    cursorContainer: document.getElementById('cursorContainer'),
    collabNotify: document.getElementById('collabNotify'),
    members: {},
    cursors: {},

    // 初始化协同
    init() {
        this.bindLocalCursorSync();
        console.log('✅ 协同模块已加载');
    },

    // 【后端调用】更新协同数据（实时推送）
    updateData(data) {
        this.members = data.members || {};
        this.cursors = data.cursors || {};
        this.renderMembers();
        this.renderCursors();
    },

    // 渲染在线成员列表
    renderMembers() {
        this.memberList.innerHTML = '';
        const count = Object.keys(this.members).length;
        this.memberCount.textContent = `${count} 人在线`;

        for (const [uid, user] of Object.entries(this.members)) {
            const item = document.createElement('div');
            item.className = 'member-item';
            item.innerHTML = `
                <span class="member-avatar" style="color: ${user.color}">${user.avatar}</span>
                <span>${user.name}</span>
            `;
            this.memberList.appendChild(item);
        }
    },

    // 渲染远端操作光标（超低延迟）
    renderCursors() {
        this.cursorContainer.innerHTML = '';
        for (const [uid, pos] of Object.entries(this.cursors)) {
            const user = this.members[uid];
            if (!user) continue;

            const cursor = document.createElement('div');
            cursor.className = 'remote-cursor';
            cursor.style.background = user.color;
            cursor.style.left = pos.x + 'px';
            cursor.style.top = pos.y + 'px';

            const label = document.createElement('div');
            label.className = 'cursor-label';
            label.style.background = user.color;
            label.textContent = user.name;
            cursor.appendChild(label);

            this.cursorContainer.appendChild(cursor);
        }
    },

    // 显示协同操作提示
    showNotify(data) {
        this.collabNotify.innerHTML = `<span style="color:${data.color}">${data.user}</span> ${data.msg}`;
        this.collabNotify.classList.add('show');
        setTimeout(() => {
            this.collabNotify.classList.remove('show');
        }, 2000);
    },

    // 同步本地光标位置到后端（暂未实现云端接口）
    bindLocalCursorSync() {}
};

// 自动初始化
document.addEventListener('DOMContentLoaded', () => {
    window.CollabUI.init();
});