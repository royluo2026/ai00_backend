using Ai00.Connector.Tray;

ApplicationConfiguration.Initialize();
using var icon = new NotifyIcon { Text = "AI00 Connector", Visible = true, Icon = SystemIcons.Application };
using var menu = new ContextMenuStrip();
using var status = new StatusView();
menu.Items.Add("配对", null, (_, _) => MessageBox.Show("请在 AI00 网页端生成配对码后输入。", "AI00 Connector"));
menu.Items.Add("状态", null, (_, _) => status.ShowStatus(new("未配对", Environment.UserName, "检测中", "检测中", "检测中", "检测中", Application.ProductVersion)));
menu.Items.Add("导出诊断", null, (_, _) => MessageBox.Show("诊断导出只包含运行状态和版本，不包含模型或凭证。", "AI00 Connector"));
menu.Items.Add("解绑", null, (_, _) => MessageBox.Show("解绑需要在 AI00 网页端确认。", "AI00 Connector"));
menu.Items.Add("退出", null, (_, _) => Application.Exit());
icon.ContextMenuStrip = menu;
Application.Run();
