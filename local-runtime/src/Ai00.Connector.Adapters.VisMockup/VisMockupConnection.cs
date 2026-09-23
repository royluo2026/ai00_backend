using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed class VisMockupConnection(IVisMockupCom com)
{
    public IVisMockupApplication RequireExistingApplication()
    {
        if(com.TryAttachExistingApplication(out var application))return application!;
        throw new ConnectorException("vismockup_unavailable");
    }
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
public sealed class BreakawayVisMockupCom(string executable,string publisher):IVisMockupCom
{
    private readonly WindowsVisMockupCom inner=new(executable);
    public VisMockupProcessState InspectProcess()=>inner.InspectProcess();
    public bool TryGetActiveApplication(out IVisMockupApplication? application)=>inner.TryGetActiveApplication(out application);
    public bool TryAttachExistingApplication(out IVisMockupApplication? application)=>inner.TryAttachExistingApplication(out application);
    public void Launch()
    {
        _ = new VisMockupBreakawayLauncher(executable,publisher).Verify();
        inner.Launch();
    }
    public void HideOwnedWindows()=>inner.HideOwnedWindows();
    public IVisMockupApplication WaitForActiveApplication(TimeSpan timeout)=>inner.WaitForActiveApplication(timeout);
}
