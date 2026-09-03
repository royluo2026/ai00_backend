using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed class VisMockupConnection(IVisMockupCom com)
{
    public IVisMockupApplication RequireActiveApplication(bool allowLaunch)
    {
        if (com.TryGetActiveApplication(out var application)) return application!;
        if (!allowLaunch) throw new ConnectorException("vismockup_unavailable");
        com.Launch();
        try { return com.WaitForActiveApplication(TimeSpan.FromSeconds(30)); }
        catch (TimeoutException) { throw new ConnectorException("vismockup_unavailable"); }
    }

    public IVisMockupDocument RequireActiveDocument(bool allowLaunch = false) =>
        RequireActiveApplication(allowLaunch).ActiveDocument
        ?? throw new ConnectorException("active_document_unavailable");
}
