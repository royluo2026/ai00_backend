namespace Ai00.Connector.Tray;

public sealed record ConnectorStatus(
    string DeviceId, string UserId, string Service, string SessionHost,
    string Adapter, string VisMockup, string Version);

public sealed class StatusView : Form
{
    private readonly Label _label = new() { Dock = DockStyle.Fill, AutoSize = false, Padding = new Padding(16) };

    public StatusView()
    {
        Text = "AI00 Connector 状态";
        ClientSize = new Size(520, 260);
        Controls.Add(_label);
    }

    public void ShowStatus(ConnectorStatus status)
    {
        _label.Text = $"设备：{status.DeviceId}\n用户：{status.UserId}\nService：{status.Service}\nSessionHost：{status.SessionHost}\nAdapter：{status.Adapter}\nVisMockup：{status.VisMockup}\n版本：{status.Version}";
        Show();
        Activate();
    }
}
