using System.Runtime.InteropServices;
using Microsoft.CSharp.RuntimeBinder;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

public interface IVisMockupCom
{
    VisMockupProcessState InspectProcess();
    bool TryGetActiveApplication(out IVisMockupApplication? application);
    void Launch();
    IVisMockupApplication WaitForActiveApplication(TimeSpan timeout);
}

public interface IVisMockupApplication
{
    string ProductVersion { get; }
    IVisMockupDocument? ActiveDocument { get; }
    IVisMockupDocument OpenDocument(string path);
    void CloseAllDocuments();
}

public interface IVisMockupDocument
{
    string DocumentId { get; }
    string SourceIdentity { get; }
    IVisMockupNode RootNode { get; }
    IReadOnlyCollection<string> AllNodeKeys { get; }
    IReadOnlyCollection<string> VisibleNodeKeys { get; }
    void SetNodeVisible(string nodeKey, bool visible);
    void SetAllNodesVisible(bool visible);
    void ApplyCaptureProfile(CaptureProfile profile);
    string AttachModel(string path);
    void CaptureImage(string path);
    void ExportPlmxml(string path, int hierarchyIndex);
    void Close();
}

public interface IVisMockupNode
{
    string NodeKey { get; }
    string PrintableName { get; }
    string OccurrenceId { get; }
    string ModelId { get; }
    IReadOnlyList<IVisMockupNode> Children { get; }
}

public sealed record VisMockupProcessState(bool Running, string ProductVersion);

internal static class VisMockupDispatch
{
    [ComImport]
    [Guid("00020400-0000-0000-C000-000000000046")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IDispatch
    {
        [PreserveSig] int GetTypeInfoCount(out uint count);
        [PreserveSig] int GetTypeInfo(uint index, uint lcid, out IntPtr typeInfo);
        [PreserveSig] int GetIDsOfNames(
            ref Guid interfaceId, IntPtr names, uint nameCount, uint lcid, IntPtr dispatchIds);
        [PreserveSig] int Invoke(
            int dispatchId, ref Guid interfaceId, uint lcid, ushort flags,
            ref DispatchParameters parameters, IntPtr result, IntPtr exceptionInfo, IntPtr argumentError);
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct DispatchParameters
    {
        public IntPtr Arguments;
        public IntPtr NamedArguments;
        public uint ArgumentCount;
        public uint NamedArgumentCount;
    }

    [DllImport("oleaut32.dll")]
    private static extern int VariantClear(IntPtr variant);

    public static object GetProperty(object value, int dispatchId, params object?[]? args)
        => Invoke(value, dispatchId, 2, allowEmptyResult: false, args: args);

    public static object InvokeMethod(object value, int dispatchId, params object?[]? args)
        => Invoke(value, dispatchId, 1, allowEmptyResult: true, args: args);

    public static uint InvokeUInt32OutParameter(object value, int dispatchId)
    {
        const int variantBytes = 32;
        const ushort variantTypeByRefUInt32 = 0x4013;
        var output = Marshal.AllocCoTaskMem(sizeof(uint));
        var argument = Marshal.AllocCoTaskMem(variantBytes);
        try
        {
            Marshal.WriteInt32(output, 0);
            for (var index = 0; index < variantBytes; index++) Marshal.WriteByte(argument, index, 0);
            Marshal.WriteInt16(argument, unchecked((short)variantTypeByRefUInt32));
            Marshal.WriteIntPtr(argument, 8, output);
            var parameters = new DispatchParameters
            {
                Arguments = argument,
                ArgumentCount = 1,
            };
            var empty = Guid.Empty;
            var hresult = ((IDispatch)value).Invoke(
                dispatchId, ref empty, 0x0409, 1, ref parameters,
                IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
            Marshal.ThrowExceptionForHR(hresult);
            return unchecked((uint)Marshal.ReadInt32(output));
        }
        catch (COMException error)
        {
            throw new ConnectorException(
                $"vismockup_dispatch_d{dispatchId}_h{unchecked((uint)error.HResult):x8}");
        }
        finally
        {
            _ = VariantClear(argument);
            Marshal.FreeCoTaskMem(argument);
            Marshal.FreeCoTaskMem(output);
        }
    }

    private static object Invoke(
        object value, int dispatchId, ushort flags, bool allowEmptyResult, object?[]? args)
    {
        var values = args ?? [];
        const int variantBytes = 32;
        var arguments = values.Length == 0 ? IntPtr.Zero : Marshal.AllocCoTaskMem(variantBytes * values.Length);
        var result = Marshal.AllocCoTaskMem(variantBytes);
        try
        {
            for (var index = 0; index < values.Length; index++)
            {
                var target = IntPtr.Add(arguments, variantBytes * index);
                Marshal.GetNativeVariantForObject(values[values.Length - index - 1], target);
            }
            for (var index = 0; index < variantBytes; index++) Marshal.WriteByte(result, index, 0);
            var parameters = new DispatchParameters
            {
                Arguments = arguments,
                ArgumentCount = (uint)values.Length,
            };
            var empty = Guid.Empty;
            var hresult = ((IDispatch)value).Invoke(
                dispatchId, ref empty, 0x0409, flags, ref parameters,
                result, IntPtr.Zero, IntPtr.Zero);
            Marshal.ThrowExceptionForHR(hresult);
            var managedResult = Marshal.GetObjectForNativeVariant(result);
            return managedResult ?? (allowEmptyResult
                ? DBNull.Value
                : throw new COMException($"VisMockup DISPID {dispatchId} returned null"));
        }
        catch (COMException error)
        {
            throw new ConnectorException(
                $"vismockup_dispatch_d{dispatchId}_h{unchecked((uint)error.HResult):x8}");
        }
        finally
        {
            _ = VariantClear(result);
            Marshal.FreeCoTaskMem(result);
            if (arguments != IntPtr.Zero)
            {
                for (var index = 0; index < values.Length; index++)
                    _ = VariantClear(IntPtr.Add(arguments, variantBytes * index));
                Marshal.FreeCoTaskMem(arguments);
            }
        }
    }
}

public sealed class WindowsVisMockupCom(string executable) : IVisMockupCom
{
    private const string ProgId = "VFFrame.Application";
    private IVisMockupApplication? _application;

    public VisMockupProcessState InspectProcess()
    {
        var path = Path.GetFullPath(executable);
        var processName = Path.GetFileNameWithoutExtension(path);
        var running = !string.IsNullOrWhiteSpace(processName) &&
            System.Diagnostics.Process.GetProcesses().Any(process => MatchesProcessName(processName, process.ProcessName));
        var version = File.Exists(path)
            ? System.Diagnostics.FileVersionInfo.GetVersionInfo(path).ProductVersion ?? "unknown"
            : "unknown";
        return new(running, version);
    }

    public bool TryGetActiveApplication(out IVisMockupApplication? application)
    {
        if (_application is not null)
        {
            application = _application;
            return true;
        }

        if (!InspectProcess().Running)
        {
            application = null;
            return false;
        }

        try
        {
            _application = AttachActive();
            application = _application;
            return true;
        }
        catch (COMException)
        {
            application = null;
            return false;
        }
    }

    internal static bool MatchesProcessName(string configuredName, string runningName) =>
        string.Equals(configuredName, runningName, StringComparison.OrdinalIgnoreCase) ||
        string.Equals(configuredName + "_NG", runningName, StringComparison.OrdinalIgnoreCase);

    public void Launch()
    {
        var path = Path.GetFullPath(executable);
        if (!File.Exists(path)) throw new FileNotFoundException("VisMockup executable not found", path);
        _application = null;
        System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(path)
        {
            UseShellExecute = true,
        });
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

    private IVisMockupApplication AttachActive()
    {
        var type = Type.GetTypeFromProgID(ProgId, throwOnError: true)!;
        var instance = Activator.CreateInstance(type)
            ?? throw new COMException("Unable to connect to VisMockup COM application");
        var installedVersion = InspectProcess().ProductVersion;
        return new DynamicApplication(instance, installedVersion);
    }

    private sealed class DynamicApplication(object value, string installedVersion) : IVisMockupApplication
    {
        private dynamic Value => value;
        // Do not query app.Version through COM. VisMockup 14.2 can block that
        // automation call indefinitely even though the application and document
        // DISPIDs are healthy. The installed executable is the authoritative,
        // non-blocking source for the adapter's advertised product version.
        public string ProductVersion => installedVersion;
        public IVisMockupDocument? ActiveDocument
        {
            get
            {
                // VFFrame.Application's generated .NET dispatch metadata returns
                // null for Documents on this VisMockup release.  The working
                // appversion bridge uses the raw automation DISPIDs instead:
                // app 4 -> document list, document list 3 -> count,
                // app 21 -> active full document.
                var documents = VisMockupDispatch.GetProperty(value, 4);
                var count = Convert.ToInt32(VisMockupDispatch.GetProperty(documents, 3));
                if (count <= 0) return null;
                var activeDocument = VisMockupDispatch.GetProperty(value, 21);
                return new DynamicDocument(
                    activeDocument,
                    VisMockupDispatch.GetProperty(activeDocument, 5));
            }
        }
        public IVisMockupDocument OpenDocument(string path) =>
            new DynamicDocument(Value.Documents.Open(path));
        public void CloseAllDocuments() => Value.Documents.CloseAllDocuments();
    }

    private sealed class DynamicDocument(object value, object? activeView = null) : IVisMockupDocument
    {
        private dynamic Value => value;
        private object ActiveView => activeView ?? Value.ActiveView;
        public string DocumentId => ReadString("FullName", "Name");
        public string SourceIdentity => ReadString("FullName", "Name");
        public IVisMockupNode RootNode => new DynamicNode(VisMockupDispatch.GetProperty(ActiveView, 11));
        public IReadOnlyCollection<string> AllNodeKeys => Traverse().Select(NodeKey).ToArray();
        public IReadOnlyCollection<string> VisibleNodeKeys => Traverse().Where(IsVisible).Select(NodeKey).ToArray();
        public void SetNodeVisible(string nodeKey, bool visible)
        {
            dynamic node = Traverse().SingleOrDefault(item => string.Equals(NodeKey(item), nodeKey, StringComparison.Ordinal))
                ?? throw new InvalidOperationException("VisMockup node not found");
            try { node.Visible = visible; }
            catch { throw new ConnectorException("visibility_control_unsupported"); }
        }
        public void SetAllNodesVisible(bool visible)
        {
            _ = VisMockupDispatch.InvokeMethod(ActiveView, visible ? 17 : 18);
        }
        public void ApplyCaptureProfile(CaptureProfile profile)
        {
            if (profile is not { Format: "png", Width: 1920, Height: 1080, Background: "current" })
                throw new ConnectorException("capture_profile_unsupported");
        }
        public string AttachModel(string path)
        {
            dynamic view = Value.ActiveView;
            dynamic created = view.AddModel(path);
            return Convert.ToString(created.GetNodeKey()) ?? throw new InvalidOperationException("Attached node has no key");
        }
        public void CaptureImage(string path) => Value.ActiveView.CaptureImage(path);
        public void ExportPlmxml(string path, int hierarchyIndex)
        {
            if (hierarchyIndex < 0) throw new ConnectorException("vismockup_hierarchy_index_invalid");
            _ = VisMockupDispatch.InvokeMethod(value, 13, 0, path, "", hierarchyIndex);
        }
        public void Close() => Value.CloseDocument();
        private List<object> Traverse()
        {
            var result = new List<object>();
            var stack = new Stack<object>();
            stack.Push(Value.ActiveView.RootNode);
            while (stack.Count > 0)
            {
                dynamic node = stack.Pop();
                result.Add(node);
                var count = Convert.ToInt32(node.NumChildren);
                dynamic children = node.Children;
                for (var index = count - 1; index >= 0; index--) stack.Push(children.Node(index));
            }
            return result;
        }
        private static string NodeKey(object value)
        {
            dynamic node = value;
            return Convert.ToString(node.GetNodeKey()) ?? "";
        }
        private static bool IsVisible(object value)
        {
            dynamic node = value;
            try { return Convert.ToBoolean(node.Visible); }
            catch { throw new ConnectorException("visibility_read_unsupported"); }
        }
        private string ReadString(string primary, string fallback)
        {
            try { return Convert.ToString(Value.GetType().InvokeMember(primary, System.Reflection.BindingFlags.GetProperty, null, value, null)) ?? ""; }
            catch { return Convert.ToString(Value.GetType().InvokeMember(fallback, System.Reflection.BindingFlags.GetProperty, null, value, null)) ?? ""; }
        }
    }

    private sealed class DynamicNode(object value) : IVisMockupNode
    {
        private dynamic Value => value;
        public string NodeKey => VisMockupDispatch.InvokeUInt32OutParameter(value, 21).ToString();
        public string PrintableName => Convert.ToString(VisMockupDispatch.GetProperty(value, 7)) ?? "";
        public string OccurrenceId { get { try { return Convert.ToString(Value.MetaDataProperties.GetPropertyByName("catiaOccurrenceName")) ?? ""; } catch { return ""; } } }
        public string ModelId { get { try { return Convert.ToString(Value.MetaDataProperties.GetPropertyByName("itemId")) ?? ""; } catch { return ""; } } }
        public IReadOnlyList<IVisMockupNode> Children
        {
            get
            {
                var count = Convert.ToInt32(VisMockupDispatch.GetProperty(value, 3));
                var children = VisMockupDispatch.GetProperty(value, 13);
                var result = new List<IVisMockupNode>(count);
                for (var index = 0; index < count; index++)
                    result.Add(new DynamicNode(VisMockupDispatch.GetProperty(children, 3, index)));
                return result;
            }
        }
    }
}
