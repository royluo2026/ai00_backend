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
    IReadOnlyList<IVisMockupDocument> OpenDocuments { get; }
    IVisMockupDocument OpenDocument(string path);
    void CloseAllDocuments();
}

public interface IVisMockupDocument
{
    string DocumentId { get; }
    string SourceIdentity { get; }
    int HierarchyCount { get; }
    IVisMockupNode RootNode { get; }
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
    string ModelId { get; }
    IReadOnlyList<IVisMockupNode> Children { get; }
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

    internal static IReadOnlyList<IVisMockupNode> MaterializeChildren(
        int count, Func<int, IVisMockupNode> childAt)
    {
        if (count <= 0) return [];
        var result = new List<IVisMockupNode>(count);
        for (var index = 0; index < count; index++)
            result.Add(childAt(index));
        return result;
    }

    public VisMockupProcessState InspectProcess()
    {
        var path = Path.GetFullPath(executable);
        var processName = Path.GetFileNameWithoutExtension(path);
        var processes = string.IsNullOrWhiteSpace(processName)
            ? []
            : System.Diagnostics.Process.GetProcessesByName(processName)
                .Concat(System.Diagnostics.Process.GetProcessesByName(processName + "_NG")).ToArray();
        var matches = new List<(int Id, long Started, bool HasMainWindow)>();
        var running = false;
        var processCount = 0;
        try
        {
            foreach (var process in processes)
            {
                running = true;
                processCount++;
                try { matches.Add((process.Id, process.StartTime.ToUniversalTime().Ticks,
                    process.MainWindowHandle != IntPtr.Zero)); }
                catch (Exception error) when (error is System.ComponentModel.Win32Exception or InvalidOperationException) { }
            }
        }
        finally { foreach (var process in processes) process.Dispose(); }
        var version = File.Exists(path)
            ? System.Diagnostics.FileVersionInfo.GetVersionInfo(path).ProductVersion ?? "unknown"
            : "unknown";
        var identity = SelectProcessIdentity(matches);
        return identity is { } selected
            ? new(true, version, selected.Id, selected.Started)
            : new(running, version);
    }

    internal static (int Id, long Started)? SelectProcessIdentity(
        IReadOnlyList<(int Id, long Started, bool HasMainWindow)> processes)
    {
        var windowed = processes.Where(process => process.HasMainWindow).ToArray();
        if (windowed.Length == 1) return (windowed[0].Id, windowed[0].Started);
        if (windowed.Length > 1 || processes.Count != 1) return null;
        return (processes[0].Id, processes[0].Started);
    }

    public bool TryGetActiveApplication(out IVisMockupApplication? application)
    {
        var process = InspectProcess();
        var identity = process.ProcessId is int pid && process.ProcessStartUtcTicks is long started
            ? (pid, started) : ((int, long)?)null;
        if (_application is not null && CanReuseCachedApplication(process, _attachedProcess))
        {
            application = _application;
            return true;
        }

        _application = null;
        _attachedProcess = null;

        if (!process.Running)
        {
            application = null;
            return false;
        }

        try
        {
            _application = AttachActive(process.ProductVersion);
            _attachedProcess = identity;
            application = _application;
            return true;
        }
        catch (COMException)
        {
            application = null;
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

    private IVisMockupApplication AttachActive(string installedVersion)
    {
        var type = Type.GetTypeFromProgID(ProgId, throwOnError: true)!;
        var instance = Activator.CreateInstance(type)
            ?? throw new COMException("Unable to connect to VisMockup COM application");
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
                var activeApplication = VisMockupDispatch.GetProperty(value, 21);
                var activeDocument = VisMockupDispatch.GetProperty(activeApplication, 4);
                return new DynamicDocument(
                    activeDocument,
                    VisMockupDispatch.GetProperty(activeApplication, 5),
                    new DynamicPlmxmlSaveOptions(
                        VisMockupDispatch.GetProperty(activeApplication, 69)));
            }
        }
        public IReadOnlyList<IVisMockupDocument> OpenDocuments
        {
            get
            {
                var documents = VisMockupDispatch.GetProperty(value, 4);
                var count = Convert.ToInt32(VisMockupDispatch.GetProperty(documents, 3));
                if (count <= 0) return [];

                // VisMockup 14.2 exposes the active full document reliably, but
                // some installations reject the documented DocByIndex dispatch
                // call.  A single open document is therefore still completely
                // enumerable without using that unstable member.
                var activeDocument = ActiveDocument;
                if (count == 1)
                    return activeDocument is null ? [] : [activeDocument];

                var activeApplication = VisMockupDispatch.GetProperty(value, 21);
                var saveOptions = new DynamicPlmxmlSaveOptions(VisMockupDispatch.GetProperty(activeApplication, 69));
                var result = new List<IVisMockupDocument>(count);
                try
                {
                    for (var index = 0; index < count; index++)
                    {
                        var document = VisMockupDispatch.GetProperty(documents, 7, index);
                        var views = VisMockupDispatch.GetProperty(document, 3);
                        if (Convert.ToInt32(VisMockupDispatch.GetProperty(views, 1)) <= 0) continue;
                        var view = VisMockupDispatch.GetProperty(views, 2, 0);
                        result.Add(new DynamicDocument(document, view, saveOptions));
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
            var previousDocumentId = ActiveDocument?.DocumentId;
            _ = Value.Documents.Open(path);
            var expectedPath = Path.GetFullPath(path);
            var deadline = DateTimeOffset.UtcNow.AddMinutes(2);
            while (DateTimeOffset.UtcNow < deadline)
            {
                var document = ActiveDocument;
                if (document is not null &&
                    (!string.Equals(document.DocumentId, previousDocumentId, StringComparison.Ordinal) ||
                     (Path.IsPathFullyQualified(document.SourceIdentity) &&
                      string.Equals(Path.GetFullPath(document.SourceIdentity), expectedPath, StringComparison.OrdinalIgnoreCase))))
                    return document;
                Thread.Sleep(250);
            }
            throw new ConnectorException("vismockup_document_open_timeout");
        }
        public void CloseAllDocuments()
        {
            var documents = VisMockupDispatch.GetProperty(value, 4);
            _ = VisMockupDispatch.InvokeMethod(documents, 2);
        }
    }

    private sealed class DynamicDocument(
        object value,
        object activeView,
        IVisMockupPlmxmlSaveOptions saveOptions) : IVisMockupDocument
    {
        private dynamic Value => value;
        private object ActiveView => activeView;
        public string DocumentId => Convert.ToString(VisMockupDispatch.GetProperty(value, 6)) ?? "";
        public string SourceIdentity => Convert.ToString(VisMockupDispatch.GetProperty(value, 11)) ?? "";
        public int HierarchyCount => Convert.ToInt32(VisMockupDispatch.GetProperty(value, 14));
        public IVisMockupNode RootNode => new DynamicNode(VisMockupDispatch.GetProperty(ActiveView, 11));
        public IReadOnlyCollection<string> AllNodeKeys => Traverse().Select(NodeKey).ToArray();
        public IReadOnlyCollection<string> VisibleNodeKeys => Traverse().Where(IsVisible).Select(NodeKey).ToArray();
        public bool IsNodeVisible(string nodeKey) => IsVisible(FindNode(nodeKey));
        public void SetNodeVisible(string nodeKey, bool visible)
        {
            var node = FindNode(nodeKey);
            // visible PUT changes a flag even for unloaded parts. The view
            // command performs the display/load operation for the selected branch.
            var nodes = VisMockupDispatch.InvokeMethod(ActiveView, 35);
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
        private dynamic Value => value;
        public string NodeKey => VisMockupDispatch.InvokeUInt32OutParameter(value, 21).ToString();
        public bool IsVisible => Convert.ToBoolean(VisMockupDispatch.GetProperty(value, 9));
        public string PrintableName => Convert.ToString(VisMockupDispatch.GetProperty(value, 7)) ?? "";
        public string OccurrenceId
        {
            get
            {
                foreach (var name in new[] { "__PLM_INST_UID", "bl_occurrence_uid", "catiaOccurrenceName" })
                {
                    try { var result = Convert.ToString(Value.MetaDataProperties.GetPropertyByName(name)) ?? "";
                        if (!string.IsNullOrWhiteSpace(result)) return result; }
                    catch { }
                }
                return "";
            }
        }
        public string ModelId { get { try { return Convert.ToString(Value.MetaDataProperties.GetPropertyByName("itemId")) ?? ""; } catch { return ""; } } }
        public IReadOnlyList<IVisMockupNode> Children
        {
            get
            {
                int count;
                try { count = Convert.ToInt32(VisMockupDispatch.GetProperty(value, 3)); }
                catch (ConnectorException error) when (error.Code == "vismockup_dispatch_d3_h80020009")
                {
                    return [];
                }
                if (count <= 0) return [];
                var children = VisMockupDispatch.GetProperty(value, 13);
                var collectionCount = Convert.ToInt32(VisMockupDispatch.GetProperty(children, 2));
                return MaterializeChildren(collectionCount,
                    index => new DynamicNode(VisMockupDispatch.GetProperty(children, 3, index)));
            }
        }
    }
}
