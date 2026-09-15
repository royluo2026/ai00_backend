namespace Ai00.Connector.Adapters.VisMockup;

internal interface ILiveHierarchyInventoryReader
{
    LiveHierarchyInventoryPage Read(
        VisMockupProcessState process,
        string documentHandle,
        string sourceIdentity,
        string documentSession,
        int startIndex,
        int pageSize,
        int maxNodes);
}
