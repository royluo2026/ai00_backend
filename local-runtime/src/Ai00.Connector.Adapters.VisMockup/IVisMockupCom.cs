using System.Runtime.InteropServices;

namespace Ai00.Connector.Adapters.VisMockup;

public interface IVisMockupCom
{
    bool TryGetActiveApplication(out IVisMockupApplication? application);
    void Launch();
    IVisMockupApplication WaitForActiveApplication(TimeSpan timeout);
}

public interface IVisMockupApplication
{
    string ProductVersion { get; }
    IVisMockupDocument? ActiveDocument { get; }
}

public interface IVisMockupDocument
{
    string DocumentId { get; }
    string SourceIdentity { get; }
    IVisMockupNode RootNode { get; }
}

public interface IVisMockupNode
{
    string NodeKey { get; }
    string PrintableName { get; }
    string OccurrenceId { get; }
    string ModelId { get; }
    IReadOnlyList<IVisMockupNode> Children { get; }
}

public sealed class WindowsVisMockupCom(string executable) : IVisMockupCom
{
    private const string ProgId = "VFFrame.Application";

    public bool TryGetActiveApplication(out IVisMockupApplication? application)
    {
        application = null;
        if (CLSIDFromProgID(ProgId, out var classId) != 0) return false;
        if (GetActiveObject(ref classId, 0, out var instance) != 0 || instance is null) return false;
        application = new DynamicApplication(instance);
        return true;
    }

    public void Launch()
    {
        var path = Path.GetFullPath(executable);
        if (!File.Exists(path)) throw new FileNotFoundException("VisMockup executable not found", path);
        System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(path) { UseShellExecute = true });
    }

    public IVisMockupApplication WaitForActiveApplication(TimeSpan timeout)
    {
        var deadline = DateTimeOffset.UtcNow + timeout;
        while (DateTimeOffset.UtcNow < deadline)
        {
            if (TryGetActiveApplication(out var application)) return application!;
            Thread.Sleep(250);
        }
        throw new TimeoutException("VisMockup active object timeout");
    }

    [DllImport("ole32.dll", CharSet = CharSet.Unicode)]
    private static extern int CLSIDFromProgID(string progId, out Guid classId);

    [DllImport("oleaut32.dll", PreserveSig = true)]
    private static extern int GetActiveObject(ref Guid classId, nint reserved, [MarshalAs(UnmanagedType.IUnknown)] out object? instance);

    private sealed class DynamicApplication(object value) : IVisMockupApplication
    {
        private dynamic Value => value;
        public string ProductVersion
        {
            get { try { return Convert.ToString(Value.Version) ?? "unknown"; } catch { return "unknown"; } }
        }
        public IVisMockupDocument? ActiveDocument
        {
            get
            {
                dynamic documents = Value.Documents;
                if (Convert.ToInt32(documents.Count) <= 0) return null;
                return new DynamicDocument(documents.Item(1));
            }
        }
    }

    private sealed class DynamicDocument(object value) : IVisMockupDocument
    {
        private dynamic Value => value;
        public string DocumentId => ReadString("FullName", "Name");
        public string SourceIdentity => ReadString("FullName", "Name");
        public IVisMockupNode RootNode => new DynamicNode(Value.ActiveView.RootNode);
        private string ReadString(string primary, string fallback)
        {
            try { return Convert.ToString(Value.GetType().InvokeMember(primary, System.Reflection.BindingFlags.GetProperty, null, value, null)) ?? ""; }
            catch { return Convert.ToString(Value.GetType().InvokeMember(fallback, System.Reflection.BindingFlags.GetProperty, null, value, null)) ?? ""; }
        }
    }

    private sealed class DynamicNode(object value) : IVisMockupNode
    {
        private dynamic Value => value;
        public string NodeKey => Convert.ToString(Value.GetNodeKey()) ?? "";
        public string PrintableName { get { try { return Convert.ToString(Value.PrintableName) ?? ""; } catch { return Convert.ToString(Value.Fullname) ?? ""; } } }
        public string OccurrenceId { get { try { return Convert.ToString(Value.MetaDataProperties.GetPropertyByName("catiaOccurrenceName")) ?? ""; } catch { return ""; } } }
        public string ModelId { get { try { return Convert.ToString(Value.MetaDataProperties.GetPropertyByName("itemId")) ?? ""; } catch { return ""; } } }
        public IReadOnlyList<IVisMockupNode> Children
        {
            get
            {
                var count = Convert.ToInt32(Value.NumChildren);
                dynamic children = Value.Children;
                var result = new List<IVisMockupNode>(count);
                for (var index = 0; index < count; index++)
                    result.Add(new DynamicNode(children.Node(index)));
                return result;
            }
        }
    }
}
