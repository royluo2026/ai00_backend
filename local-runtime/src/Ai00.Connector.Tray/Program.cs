using Ai00.Connector.Tray;
using System.Security.Principal;

ApplicationConfiguration.Initialize();
if (args.Length == 1 && Uri.TryCreate(args[0], UriKind.Absolute, out var pairingUri))
{
    try
    {
        await PairingPipeClient.ForwardAsync(pairingUri);
    }
    catch (Exception error)
    {
        MessageBox.Show($"连接 AI00 Connector 失败：{error.Message}", "AI00 Connector");
    }
    return;
}
using var icon = new NotifyIcon { Text = "AI00 Connector", Visible = true, Icon = SystemIcons.Application };
var windowsSid = WindowsIdentity.GetCurrent().User?.Value
    ?? throw new InvalidOperationException("Current Windows SID is unavailable");
using var brokerCancellation = new CancellationTokenSource();
var broker = new SessionHostBroker(windowsSid).RunAsync(brokerCancellation.Token);
using var menu = new ContextMenuStrip();
using var status = new StatusView();
menu.Items.Add("配对", null, (_, _) => MessageBox.Show("请从 AI00 数模仿真页面点击“连接本机”。", "AI00 Connector"));
menu.Items.Add("状态", null, (_, _) => status.ShowStatus(new("未配对", Environment.UserName, "检测中", "检测中", "检测中", "检测中", Application.ProductVersion)));
menu.Items.Add("导出诊断", null, (_, _) => MessageBox.Show("诊断导出只包含运行状态和版本，不包含模型或凭证。", "AI00 Connector"));
menu.Items.Add("解绑", null, (_, _) => MessageBox.Show("解绑需要在 AI00 网页端确认。", "AI00 Connector"));
menu.Items.Add("退出", null, (_, _) => Application.Exit());
icon.ContextMenuStrip = menu;
Application.Run();
brokerCancellation.Cancel();
try { await broker; } catch (OperationCanceledException) { }
