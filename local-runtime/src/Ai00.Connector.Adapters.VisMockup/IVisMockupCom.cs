using System.Runtime.InteropServices;
using Microsoft.CSharp.RuntimeBinder;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

public interface IVisMockupCom
{
    VisMockupProcessState InspectProcess();
    bool TryGetActiveApplication(out IVisMockupApplication? application);
    bool TryAttachExistingApplication(out IVisMockupApplication? application)
        => TryGetActiveApplication(out application);
    void Launch();
    void HideOwnedWindows() { }
    IVisMockupApplication WaitForActiveApplication(TimeSpan timeout);
}

public interface IVisMockupApplication
{
    string ProductVersion { get; }
    IVisMockupDocument? ActiveDocument { get; }
    IReadOnlyList<IVisMockupDocument> OpenDocuments { get; }
    IVisMockupDocument OpenDocument(string path);
    void CloseAllDocuments();
}

public interface IVisMockupDocument
{
    NativeDocumentWindow LocateNativeWindow(int processId,NativeDocumentWindow? previous)=>throw new ConnectorException("vismockup_document_window_unavailable");
    NativeDocumentWindow SelectExistingNativeWindow(int processId)=>throw new ConnectorException("vismockup_document_window_unavailable");
    NativeDocumentWindow ActivateNativeWindow(int processId,NativeDocumentWindow target)=>throw new ConnectorException("vismockup_document_window_unavailable");
    string DocumentId { get; }
    string SourceIdentity { get; }
    int HierarchyCount { get; }
    IVisMockupNode RootNode { get; }
    IVisMockupNode FindNodeByKey(string nodeKey) => throw new ConnectorException("vismockup_node_lookup_unsupported");
    IVisMockupNode FindNodeByCadId(string cadId) => throw new ConnectorException("vismockup_cad_lookup_unavailable");
    IReadOnlyCollection<string> AllNodeKeys { get; }
    IReadOnlyCollection<string> VisibleNodeKeys { get; }
    bool IsNodeVisible(string nodeKey);
    void SetNodeVisible(string nodeKey, bool visible);
    void SetNodeSelected(string nodeKey, bool selected);
    void SetAllNodesVisible(bool visible);
    void ApplyCaptureProfile(CaptureProfile profile);
    string AttachModel(string path);
    string InsertDocument(string path);
    IReadOnlyList<string> InsertedDocumentPaths { get; }
    void CaptureImage(string path);
    void ExportPlmxml(string path, int hierarchyIndex);
    void Close();
}

public interface IVisMockupNode
{
    string NodeKey { get; }
    bool IsVisible { get; }
    string PrintableName { get; }
    string OccurrenceId { get; }
    IReadOnlyList<string> OccurrenceIds
    {
        get
        {
            var occurrence = OccurrenceId;
            return string.IsNullOrWhiteSpace(occurrence) ? [] : [occurrence];
        }
    }
    string CadId => "";
    string ModelId { get; }
    IReadOnlyList<IVisMockupNode> Children { get; }
    int ChildCount => Children.Count;
    IReadOnlyList<IVisMockupNode> GetChildren(int maximum)
    {
        var children=Children;
        if(children.Count>maximum)throw new ConnectorNoEffectException("viewer_mapping_budget_exceeded");
        return children;
    }
}

internal interface IVisMockupPlmxmlSaveOptions
{
    int SaveExtendedInPlmxml { get; set; }
    int CopyParts { get; set; }
    int RetainReferences { get; set; }
    int AskEveryTime { get; set; }
    int SaveInsertedAssemblies { get; set; }
    int ForceRetainReferences { get; set; }
    int SaveLateLoadedProperties { get; set; }
}

internal static class VisMockupPlmxmlExport
{
    public static void Run(
        IVisMockupPlmxmlSaveOptions options,
        int hierarchyIndex,
        Action<int, int> export)
    {
        var original = new[]
        {
            options.SaveExtendedInPlmxml,
            options.CopyParts,
            options.RetainReferences,
            options.AskEveryTime,
            options.SaveInsertedAssemblies,
            options.ForceRetainReferences,
            options.SaveLateLoadedProperties,
        };
        try
        {
            options.SaveExtendedInPlmxml = 0;
            options.CopyParts = 0;
            options.RetainReferences = 1;
            options.AskEveryTime = 0;
            options.SaveInsertedAssemblies = 0;
            options.ForceRetainReferences = 1;
            options.SaveLateLoadedProperties = 0;
            export(2, hierarchyIndex);
        }
        finally
        {
            options.SaveExtendedInPlmxml = original[0];
            options.CopyParts = original[1];
            options.RetainReferences = original[2];
            options.AskEveryTime = original[3];
            options.SaveInsertedAssemblies = original[4];
            options.ForceRetainReferences = original[5];
            options.SaveLateLoadedProperties = original[6];
        }
    }
}

public sealed record VisMockupProcessState(
    bool Running, string ProductVersion, int? ProcessId = null, long? ProcessStartUtcTicks = null);

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

    public static object InvokeMethodWithResult(object value, int dispatchId, params object?[]? args)
        => Invoke(value, dispatchId, 1, allowEmptyResult: false, args: args);

    public static void SetProperty(object value, int dispatchId, object? propertyValue)
    {
        const int variantBytes = 32;
        const int dispatchPropertyPut = -3;
        var argument = Marshal.AllocCoTaskMem(variantBytes);
        var namedArgument = Marshal.AllocCoTaskMem(sizeof(int));
        try
        {
            for (var index = 0; index < variantBytes; index++) Marshal.WriteByte(argument, index, 0);
            Marshal.GetNativeVariantForObject(propertyValue, argument);
            Marshal.WriteInt32(namedArgument, dispatchPropertyPut);
            var parameters = new DispatchParameters
            {
                Arguments = argument,
                NamedArguments = namedArgument,
                ArgumentCount = 1,
                NamedArgumentCount = 1,
            };
            var empty = Guid.Empty;
            var hresult = ((IDispatch)value).Invoke(
                dispatchId, ref empty, 0x0409, 4, ref parameters,
                IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
            Marshal.ThrowExceptionForHR(hresult);
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
            Marshal.FreeCoTaskMem(namedArgument);
        }
    }

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
        var result = allowEmptyResult ? IntPtr.Zero : Marshal.AllocCoTaskMem(variantBytes);
        try
        {
            for (var index = 0; index < values.Length; index++)
            {
                var target = IntPtr.Add(arguments, variantBytes * index);
                for (var offset = 0; offset < variantBytes; offset++) Marshal.WriteByte(target, offset, 0);
                Marshal.GetNativeVariantForObject(values[values.Length - index - 1], target);
            }
            if (result != IntPtr.Zero)
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
            if (allowEmptyResult) return DBNull.Value;
            return Marshal.GetObjectForNativeVariant(result)
                ?? throw new COMException($"VisMockup DISPID {dispatchId} returned null");
        }
        catch (COMException error)
        {
            throw new ConnectorException(
                $"vismockup_dispatch_d{dispatchId}_h{unchecked((uint)error.HResult):x8}");
        }
        finally
        {
            if (result != IntPtr.Zero)
            {
                _ = VariantClear(result);
                Marshal.FreeCoTaskMem(result);
            }
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
    private (int ProcessId, long Started)? _attachedProcess;
    [DllImport("oleaut32.dll", PreserveSig=true)]
    private static extern int GetActiveObject(ref Guid clsid,nint reserved,
        [MarshalAs(UnmanagedType.IUnknown)] out object value);

    private delegate bool EnumWindowsCallback(IntPtr window, IntPtr state);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool EnumWindows(EnumWindowsCallback callback, IntPtr state);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ShowWindow(IntPtr window, int command);

    internal static IReadOnlyList<IVisMockupNode> MaterializeChildren(
        int count, Func<int, IVisMockupNode> childAt)
    {
        if (count <= 0) return [];
        var result = new List<IVisMockupNode>(count);
        for (var index = 0; index < count; index++)
            result.Add(childAt(index));
        return result;
    }

    internal static bool MatchesOpenedSource(IVisMockupDocument document,string expectedPath,
        TeamcenterVisualizationSource? teamcenterSource)
    {
        var source=document.SourceIdentity;
        if(Path.IsPathFullyQualified(source))
            return string.Equals(Path.GetFullPath(source),expectedPath,StringComparison.OrdinalIgnoreCase);
        // The native VVI source is a TC identity, not the temporary VVI path.
        // Never use a title/filename alone or merely a different active handle.
        return teamcenterSource is {DocumentUid.Length: >0}
            && source.Contains("?VisDoc_UID=",StringComparison.Ordinal)
            && teamcenterSource.Matches(source);
    }

    public VisMockupProcessState InspectProcess()
    {
        var path = Path.GetFullPath(executable);
        var version = File.Exists(path)
            ? System.Diagnostics.FileVersionInfo.GetVersionInfo(path).ProductVersion ?? "unknown"
            : "unknown";
        if (_attachedProcess is not { } owned) return new(false, version);
        try
        {
            using var process = System.Diagnostics.Process.GetProcessById(owned.ProcessId);
            if (process.StartTime.ToUniversalTime().Ticks == owned.Started)
                return new(true, version, owned.ProcessId, owned.Started);
        }
        catch (Exception error) when (error is ArgumentException or
            System.ComponentModel.Win32Exception or InvalidOperationException) { }
        _application = null;
        _attachedProcess = null;
        return new(false, version);
    }

    internal static (int Id, long Started)? SelectProcessIdentity(
        IReadOnlyList<(int Id, long Started, bool HasMainWindow)> processes,
        (int ProcessId, long Started)? attachedProcess = null)
    {
        if (attachedProcess is { } attached
            && processes.Any(process => process.Id == attached.ProcessId && process.Started == attached.Started))
            return (attached.ProcessId, attached.Started);
        var windowed = processes.Where(process => process.HasMainWindow).ToArray();
        if (windowed.Length == 1) return (windowed[0].Id, windowed[0].Started);
        if (windowed.Length > 1 || processes.Count != 1) return null;
        return (processes[0].Id, processes[0].Started);
    }

    public bool TryGetActiveApplication(out IVisMockupApplication? application)
    {
        if (_application is not null && InspectProcess().Running)
        {
            application = _application;
            return true;
        }
        application = null;
        return false;
    }

    public bool TryAttachExistingApplication(out IVisMockupApplication? application)
    {
        if(TryGetActiveApplication(out application))return true;
        application=null;
        try
        {
            var type=Type.GetTypeFromProgID(ProgId,throwOnError:true)!;
            var clsid=type.GUID;
            if(GetActiveObject(ref clsid,0,out var outer)!=0)return false;
            var inner=VisMockupDispatch.GetProperty(outer,21);
            var pid=Convert.ToInt32(VisMockupDispatch.GetProperty(inner,51));
            using var process=System.Diagnostics.Process.GetProcessById(pid);
            var actualPath=process.MainModule?.FileName??"";
            var configured=Path.GetFullPath(executable);
            if(!string.Equals(Path.GetDirectoryName(actualPath),Path.GetDirectoryName(configured),StringComparison.OrdinalIgnoreCase)
                ||!MatchesProcessName(Path.GetFileNameWithoutExtension(configured),process.ProcessName))return false;
            var started=process.StartTime.ToUniversalTime().Ticks;
            var version=System.Diagnostics.FileVersionInfo.GetVersionInfo(configured).ProductVersion??"unknown";
            _application=new DynamicApplication(outer,inner,version);
            _attachedProcess=(pid,started);
            application=_application;
            return true;
        }
        catch(Exception error) when(error is COMException or ArgumentException or InvalidOperationException
            or System.ComponentModel.Win32Exception or ConnectorException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    internal static bool CanReuseCachedApplication(VisMockupProcessState process, (int ProcessId, long Started)? attached) =>
        process.Running && (process.ProcessId is not int pid || process.ProcessStartUtcTicks is not long started ||
            attached == (pid, started));

    internal static bool MatchesProcessName(string configuredName, string runningName) =>
        string.Equals(configuredName, runningName, StringComparison.OrdinalIgnoreCase) ||
        string.Equals(configuredName + "_NG", runningName, StringComparison.OrdinalIgnoreCase);

    public void Launch()
    {
        var path = Path.GetFullPath(executable);
        if (!File.Exists(path)) throw new FileNotFoundException("VisMockup executable not found", path);
        _application = null;
        _attachedProcess = null;
        var type = Type.GetTypeFromProgID(ProgId, throwOnError: true)!;
        var outer = Activator.CreateInstance(type)
            ?? throw new COMException("Unable to create owned VisMockup COM application");
        var inner = VisMockupDispatch.GetProperty(outer, 21);
        var processId = Convert.ToInt32(VisMockupDispatch.GetProperty(inner, 51));
        using var process = System.Diagnostics.Process.GetProcessById(processId);
        var started = process.StartTime.ToUniversalTime().Ticks;
        var version = System.Diagnostics.FileVersionInfo.GetVersionInfo(path).ProductVersion ?? "unknown";
        _application = new DynamicApplication(outer, inner, version);
        _attachedProcess = (processId, started);
        // Teamcenter's official runner discovers a VFFrame instance only after
        // it is registered as visible. Keep that COM state, but immediately
        // suppress every top-level window belonging to the exact owned PID.
        VisMockupDispatch.SetProperty(outer, 1, true);
        HideOwnedWindows();
    }

    public void HideOwnedWindows()
    {
        if (_attachedProcess is not { ProcessId: > 0 } owned) return;
        _ = EnumWindows((window, state) =>
        {
            _ = GetWindowThreadProcessId(window, out var processId);
            if (processId == owned.ProcessId) _ = ShowWindow(window, 0);
            return true;
        }, IntPtr.Zero);
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

    private sealed class DynamicApplication(
        object value, object activeApplication, string installedVersion) : IVisMockupApplication
    {
        // Do not query app.Version through COM. VisMockup 14.2 can block that
        // automation call indefinitely even though the application and document
        // DISPIDs are healthy. The installed executable is the authoritative,
        // non-blocking source for the adapter's advertised product version.
        public string ProductVersion => installedVersion;
        public IVisMockupDocument? ActiveDocument
            => ReadActiveDocument();

        private IVisMockupDocument? ReadActiveDocument()
        {
            object activeDocument;
            try
            {
                // Teamcenter's runner loads into the retained inner application.
                // Its outer document collection can remain stale at zero, so the
                // inner active document is authoritative when this call succeeds.
                activeDocument = VisMockupDispatch.GetProperty(activeApplication, 4);
            }
            catch (ConnectorException error) when (
                error.Code.StartsWith("vismockup_dispatch_d4_", StringComparison.Ordinal))
            {
                // A blank owned process has no inner active document. Confirm
                // that state through the outer collection; otherwise preserve
                // the automation failure instead of reporting a false blank.
                var documents = VisMockupDispatch.GetProperty(value, 4);
                var count = Convert.ToInt32(VisMockupDispatch.GetProperty(documents, 3));
                if (count <= 0) return null;
                throw;
            }
            return new DynamicDocument(
                activeDocument,
                VisMockupDispatch.GetProperty(activeApplication, 5),
                new DynamicPlmxmlSaveOptions(
                    VisMockupDispatch.GetProperty(activeApplication, 69)),
                ReadActiveDocumentId);
        }
        public IReadOnlyList<IVisMockupDocument> OpenDocuments
        {
            get
            {
                var documents = VisMockupDispatch.GetProperty(activeApplication, 3);
                var count = Convert.ToInt32(VisMockupDispatch.GetProperty(documents, 3));
                var activeDocument = ActiveDocument;
                if (count <= 0) return activeDocument is null ? [] : [activeDocument];

                // VisMockup 14.2 exposes the active full document reliably, but
                // some installations reject the documented DocByIndex dispatch
                // call.  A single open document is therefore still completely
                // enumerable without using that unstable member.
                if (count == 1)
                    return activeDocument is null ? [] : [activeDocument];

                var saveOptions = new DynamicPlmxmlSaveOptions(VisMockupDispatch.GetProperty(activeApplication, 69));
                var result = new List<IVisMockupDocument>(count);
                try
                {
                    // IVisDispDocList and IVisDispViewList use one-based indices.
                    for (var index = 1; index <= count; index++)
                    {
                        var document = VisMockupDispatch.GetProperty(documents, 7, index);
                        var views = VisMockupDispatch.GetProperty(document, 3);
                        if (Convert.ToInt32(VisMockupDispatch.GetProperty(views, 1)) <= 0) continue;
                        var view = VisMockupDispatch.GetProperty(views, 2, 1);
                        result.Add(new DynamicDocument(document, view, saveOptions, ReadActiveDocumentId));
                    }
                }
                catch (Exception error) when (error is not ConnectorException)
                {
                    // With multiple documents we must not mistake an incomplete
                    // enumeration for proof that the target document is closed.
                    throw new ConnectorException("vismockup_document_enumeration_unavailable");
                }
                return result;
            }
        }
        public IVisMockupDocument OpenDocument(string path)
        {
            var expectedPath = Path.GetFullPath(path);
            var source=string.Equals(Path.GetExtension(path),".vvi",StringComparison.OrdinalIgnoreCase)
                ? TeamcenterVisualizationSource.ReadMaterial(path) : null;
            var documents = VisMockupDispatch.GetProperty(value, 4);
            _ = VisMockupDispatch.InvokeMethod(documents, 5, path);
            var deadline = DateTimeOffset.UtcNow.AddMinutes(2);
            while (DateTimeOffset.UtcNow < deadline)
            {
                var document = ActiveDocument;
                if (document is not null && MatchesOpenedSource(document,expectedPath,source))
                    return document;
                Thread.Sleep(250);
            }
            throw new ConnectorException("vismockup_document_open_timeout");
        }
        public void CloseAllDocuments()
        {
            var documents = VisMockupDispatch.GetProperty(value, 4);
            _ = VisMockupDispatch.InvokeMethod(documents, 4);
        }
        private string ReadActiveDocumentId()
        {
            var document=VisMockupDispatch.GetProperty(activeApplication,4);
            return Convert.ToString(VisMockupDispatch.GetProperty(document,6))??"";
        }
    }

    private sealed class DynamicDocument(
        object value,
        object activeView,
        IVisMockupPlmxmlSaveOptions saveOptions,
        Func<string> activeDocumentId) : IVisMockupDocument
    {
        private dynamic Value => value;
        private object ActiveView => activeView;
        public NativeDocumentWindow LocateNativeWindow(int processId,NativeDocumentWindow? previous)
            =>NativeDocumentWindow.CaptureActive(processId,DocumentId,activeDocumentId,previous);
        public NativeDocumentWindow SelectExistingNativeWindow(int processId)
            =>NativeDocumentWindow.FindAndCapture(processId,DocumentId,activeDocumentId);
        public NativeDocumentWindow ActivateNativeWindow(int processId,NativeDocumentWindow target)
            =>NativeDocumentWindow.Activate(processId,DocumentId,activeDocumentId,target);
        public string DocumentId => Convert.ToString(VisMockupDispatch.GetProperty(value, 6)) ?? "";
        public string SourceIdentity => Convert.ToString(VisMockupDispatch.GetProperty(value, 11)) ?? "";
        public int HierarchyCount => Convert.ToInt32(VisMockupDispatch.GetProperty(value, 14));
        public IVisMockupNode RootNode => new DynamicNode(VisMockupDispatch.GetProperty(ActiveView, 11));
        public IVisMockupNode FindNodeByKey(string nodeKey) => new DynamicNode(FindNode(nodeKey));
        public IVisMockupNode FindNodeByCadId(string cadId)
        {
            dynamic view = ActiveView;
            object found = null!;
            view.GetNodeFromCADID(cadId, ref found);
            if (found is null) throw new ConnectorNoEffectException("vismockup_cad_instance_unmapped");
            return new DynamicNode(found);
        }
        public IReadOnlyCollection<string> AllNodeKeys => Traverse().Select(NodeKey).ToArray();
        public IReadOnlyCollection<string> VisibleNodeKeys => Traverse().Where(IsVisible).Select(NodeKey).ToArray();
        public bool IsNodeVisible(string nodeKey) => IsVisible(FindNode(nodeKey));
        public void SetNodeVisible(string nodeKey, bool visible)
        {
            var node = FindNode(nodeKey);
            // visible PUT changes a flag even for unloaded parts. The view
            // command performs the display/load operation for the selected branch.
            var nodes = VisMockupDispatch.InvokeMethodWithResult(ActiveView, 35);
            VisMockupDispatch.InvokeMethod(nodes, 4, node);
            VisMockupDispatch.InvokeMethod(ActiveView, visible ? 19 : 20, nodes);
            VisMockupDispatch.InvokeMethod(ActiveView, 31);
        }
        public void SetNodeSelected(string nodeKey, bool selected)
        {
            var node = FindNode(nodeKey);
            VisMockupDispatch.SetProperty(node, 10, selected);
            VisMockupDispatch.InvokeMethod(ActiveView, 31);
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
        public IReadOnlyList<string> InsertedDocumentPaths
        {
            get
            {
                var count = Convert.ToInt32(VisMockupDispatch.GetProperty(value, 8));
                var result = new List<string>(count);
                for (var index = 0; index < count; index++)
                    result.Add(Convert.ToString(VisMockupDispatch.GetProperty(value, 12, index)) ?? "");
                return result;
            }
        }
        public string InsertDocument(string path)
        {
            _ = VisMockupDispatch.InvokeMethod(value, 1, path);
            var expected = Path.GetFullPath(path);
            var deadline = DateTimeOffset.UtcNow.AddMinutes(2);
            while (DateTimeOffset.UtcNow < deadline)
            {
                var inserted = InsertedDocumentPaths.FirstOrDefault(item =>
                    Path.IsPathFullyQualified(item) &&
                    string.Equals(Path.GetFullPath(item), expected, StringComparison.OrdinalIgnoreCase));
                if (inserted is not null) return inserted;
                Thread.Sleep(250);
            }
            throw new ConnectorException("vismockup_document_insert_timeout");
        }
        // VisAutomation.tlb: IVisDisp3DView.CaptureImage is DISPID 27.
        public void CaptureImage(string path) =>
            _ = VisMockupDispatch.InvokeMethod(ActiveView, 27, path);
        public void ExportPlmxml(string path, int hierarchyIndex)
        {
            if (hierarchyIndex < 0) throw new ConnectorException("vismockup_hierarchy_index_invalid");
            VisMockupPlmxmlExport.Run(saveOptions, hierarchyIndex, (saveType, selectedHierarchy) =>
                Value.ExportEx(saveType, path, "", selectedHierarchy));
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
            return Convert.ToBoolean(VisMockupDispatch.GetProperty(value, 9));
        }
        private object FindNode(string nodeKey)
        {
            if (!uint.TryParse(nodeKey, out var numericKey))
                throw new ConnectorException("vismockup_node_key_invalid");
            try
            {
                dynamic view = ActiveView;
                object? found = null;
                view.GetNodeFromKey(numericKey, ref found);
                return found ?? throw new ConnectorException("vismockup_node_not_found");
            }
            catch (ConnectorException) { throw; }
            catch { throw new ConnectorException("vismockup_node_lookup_unsupported"); }
        }
    }

    private sealed class DynamicPlmxmlSaveOptions(object value) : IVisMockupPlmxmlSaveOptions
    {
        public int SaveExtendedInPlmxml
        {
            get => Read(1);
            set => Write(1, value);
        }
        public int CopyParts
        {
            get => Read(2);
            set => Write(2, value);
        }
        public int RetainReferences
        {
            get => Read(3);
            set => Write(3, value);
        }
        public int AskEveryTime
        {
            get => Read(4);
            set => Write(4, value);
        }
        public int SaveInsertedAssemblies
        {
            get => Read(6);
            set => Write(6, value);
        }
        public int ForceRetainReferences
        {
            get => Read(7);
            set => Write(7, value);
        }
        public int SaveLateLoadedProperties
        {
            get => Read(8);
            set => Write(8, value);
        }

        private int Read(int dispatchId) => Convert.ToInt32(VisMockupDispatch.GetProperty(value, dispatchId));
        private void Write(int dispatchId, int option) => VisMockupDispatch.SetProperty(value, dispatchId, option);
    }

    private sealed class DynamicNode(object value) : IVisMockupNode
    {
        private static readonly string[] OccurrenceMetadataNames =
        [
            "bl_occurrence_uid", "__PLM_INST_UID", "__PLM_CLONE_STABLE_INST_UID",
            "__PLM_INST_TH_UID", "catiaOccurrenceName"
        ];
        private readonly Dictionary<string, string> _occurrenceMetadata = new(StringComparer.Ordinal);
        private dynamic Value => value;
        public string NodeKey => VisMockupDispatch.InvokeUInt32OutParameter(value, 21).ToString();
        public bool IsVisible => Convert.ToBoolean(VisMockupDispatch.GetProperty(value, 9));
        public string PrintableName => Convert.ToString(VisMockupDispatch.GetProperty(value, 7)) ?? "";
        // CADID is the viewer's occurrence path, not a display label or a runtime node key.
        // Unlike MetaDataProperties this does not open the JT payload.
        public string CadId => (Convert.ToString(VisMockupDispatch.GetProperty(value, 19)) ?? "").TrimEnd('\0');
        public string OccurrenceId
        {
            get
            {
                foreach (var name in OccurrenceMetadataNames)
                {
                    var candidate = ReadOccurrenceMetadata(name);
                    if (!string.IsNullOrWhiteSpace(candidate)) return candidate;
                }
                return "";
            }
        }
        public IReadOnlyList<string> OccurrenceIds
        {
            get
            {
                var result = new List<string>();
                foreach (var name in OccurrenceMetadataNames)
                {
                    var candidate = ReadOccurrenceMetadata(name);
                    if (!string.IsNullOrWhiteSpace(candidate) && !result.Contains(candidate, StringComparer.Ordinal)) result.Add(candidate);
                }
                return result;
            }
        }
        private string ReadOccurrenceMetadata(string name)
        {
            if (_occurrenceMetadata.TryGetValue(name, out var known)) return known;
            try { known = (Convert.ToString(Value.MetaDataProperties.GetPropertyByName(name)) ?? "").Trim(); }
            catch { known = ""; }
            return _occurrenceMetadata[name] = known;
        }
        public string ModelId { get { try { return Convert.ToString(Value.MetaDataProperties.GetPropertyByName("itemId")) ?? ""; } catch { return ""; } } }
        public IReadOnlyList<IVisMockupNode> Children => GetChildren(int.MaxValue);
        public int ChildCount
        {
            get
            {
                try { return Convert.ToInt32(VisMockupDispatch.GetProperty(value, 3)); }
                catch (ConnectorException error) when (error.Code == "vismockup_dispatch_d3_h80020009") { return 0; }
            }
        }
        public IReadOnlyList<IVisMockupNode> GetChildren(int maximum)
        {
                var count = ChildCount;
                if (count <= 0) return [];
                if(count>maximum)throw new ConnectorNoEffectException("viewer_mapping_budget_exceeded");
                var children = VisMockupDispatch.GetProperty(value, 13);
                var collectionCount = Convert.ToInt32(VisMockupDispatch.GetProperty(children, 2));
                if(collectionCount>maximum)throw new ConnectorNoEffectException("viewer_mapping_budget_exceeded");
                return MaterializeChildren(collectionCount,
                    index => new DynamicNode(VisMockupDispatch.GetProperty(children, 3, index)));
        }
    }
}
