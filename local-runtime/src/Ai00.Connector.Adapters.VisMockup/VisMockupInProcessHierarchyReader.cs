using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

internal sealed class VisMockupInProcessHierarchyReader(string stateRoot) : ILiveHierarchyInventoryReader
{
    private const string SupportedVis3dSha256 = "7DDD315F17FD9C0295D9D596E1C176FA1B807C09F2B55BF3FC5046A6A43CD736";
    private const string BridgeSha256 = "FD3CED5FE3A7AEA12F594054F2A0B493A4CD4839B08A43B917135F67217952CF";
    private const uint ProcessAccess = 0x0002 | 0x0400 | 0x0008 | 0x0020 | 0x0010;
    private const uint MemCommitReserve = 0x1000 | 0x2000;
    private const uint PageReadWrite = 0x04;
    private const uint MemRelease = 0x8000;
    private const uint InfiniteTimeoutGuardMs = 20_000;
    private const uint DontResolveDllReferences = 0x00000001;

    public LiveHierarchyInventoryPage Read(VisMockupProcessState process, string documentHandle,
        string sourceIdentity, string documentSession, int startIndex, int pageSize, int maxNodes)
    {
        if (!OperatingSystem.IsWindows()) throw new ConnectorException("vismockup_native_bridge_unsupported");
        if (process.ProcessId is not > 0 || process.ProcessStartUtcTicks is not > 0)
            throw new ConnectorException("vismockup_process_identity_unavailable");
        using var target = Process.GetProcessById(process.ProcessId.Value);
        if (target.StartTime.ToUniversalTime().Ticks != process.ProcessStartUtcTicks.Value)
            throw new ConnectorException("vismockup_process_identity_changed");

        var vis3d = FindModule(target, "Vis3D.dll")
            ?? throw new ConnectorException("vismockup_native_bridge_vis3d_unavailable");
        VerifyHash(vis3d.FileName, SupportedVis3dSha256, "vismockup_native_bridge_version_unsupported");
        var bridgePath = Path.Combine(AppContext.BaseDirectory, "Ai00.VisMockup.HierarchyBridge.fd3ced5f.dll");
        VerifyHash(bridgePath, BridgeSha256, "vismockup_native_bridge_integrity_failed");

        Directory.CreateDirectory(stateRoot);
        var nonce = Guid.NewGuid().ToString("N");
        var requestPath = Path.GetFullPath(Path.Combine(stateRoot, nonce + ".request"));
        var responsePath = Path.GetFullPath(Path.Combine(stateRoot, nonce + ".response"));
        File.WriteAllText(requestPath,
            sourceIdentity.Replace("\r", "", StringComparison.Ordinal).Replace("\n", "", StringComparison.Ordinal) + "\n" +
            responsePath + "\n" + startIndex + "\n" + pageSize + "\n" + maxNodes + "\n",
            new UTF8Encoding(false));
        try
        {
            InvokeBridge(target, bridgePath, requestPath);
            if (!File.Exists(responsePath)) throw new ConnectorException("vismockup_native_bridge_response_missing");
            var response = JsonSerializer.Deserialize<BridgeResponse>(File.ReadAllText(responsePath, Encoding.UTF8),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true,
                    PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower })
                ?? throw new ConnectorException("vismockup_native_bridge_response_invalid");
            if (!string.Equals(response.Status, "ok", StringComparison.Ordinal))
                throw new ConnectorException("vismockup_native_bridge_" + NormalizeCode(response.Status));
            if (!string.Equals(response.SourceIdentity, sourceIdentity, StringComparison.Ordinal))
                throw new ConnectorException("vismockup_document_changed");
            var hierarchies = (response.Hierarchies ?? []).Select(item =>
            {
                var nodes = item.Nodes ?? [];
                var hash = CanonicalJson.Hash(new { native_index = item.NativeIndex, name = item.Name, nodes });
                return new LiveHierarchyInventoryItem(item.NativeIndex, item.Name ?? $"备选层次结构 {item.NativeIndex}",
                    hash, nodes, item.Complete);
            }).ToArray();
            var consumed = hierarchies.Length;
            var next = startIndex + consumed < response.TotalHierarchies ? startIndex + consumed : (int?)null;
            return new(documentSession, startIndex, next, response.TotalHierarchies, hierarchies);
        }
        finally
        {
            TryDelete(requestPath);
            TryDelete(responsePath);
        }
    }

    private static void InvokeBridge(Process target, string bridgePath, string requestPath)
    {
        var process = OpenProcess(ProcessAccess, false, target.Id);
        if (process == IntPtr.Zero) throw new ConnectorException("vismockup_native_bridge_process_access_denied");
        try
        {
            var remoteModule = FindModule(target, Path.GetFileName(bridgePath));
            if (remoteModule is null)
            {
                RunRemote(process, RemoteKernelAddress(target, "LoadLibraryW"), bridgePath, unicode: true,
                    "vismockup_native_bridge_load_failed");
                target.Refresh();
                remoteModule = FindModule(target, Path.GetFileName(bridgePath))
                    ?? throw new ConnectorException("vismockup_native_bridge_load_failed");
            }
            var localModule = LoadLibraryExW(bridgePath, IntPtr.Zero, DontResolveDllReferences);
            if (localModule == IntPtr.Zero) throw new ConnectorException("vismockup_native_bridge_load_failed");
            try
            {
                var localEntry = GetProcAddress(localModule, "Ai00ReadHierarchy");
                if (localEntry == IntPtr.Zero) throw new ConnectorException("vismockup_native_bridge_entry_missing");
                var offset = localEntry.ToInt64() - localModule.ToInt64();
                var remoteEntry = new IntPtr(remoteModule.BaseAddress.ToInt64() + offset);
                RunRemote(process, remoteEntry, requestPath, unicode: true, "vismockup_native_bridge_read_failed");
            }
            finally { FreeLibrary(localModule); }
        }
        finally { CloseHandle(process); }
    }

    private static IntPtr RemoteKernelAddress(Process target, string export)
    {
        var remoteKernel = FindModule(target, "kernel32.dll")
            ?? throw new ConnectorException("vismockup_native_bridge_kernel_unavailable");
        var localKernel = GetModuleHandleW("kernel32.dll");
        var localExport = GetProcAddress(localKernel, export);
        if (localKernel == IntPtr.Zero || localExport == IntPtr.Zero)
            throw new ConnectorException("vismockup_native_bridge_kernel_unavailable");
        return new IntPtr(remoteKernel.BaseAddress.ToInt64() + localExport.ToInt64() - localKernel.ToInt64());
    }

    private static void RunRemote(IntPtr process, IntPtr entry, string argument, bool unicode, string errorCode)
    {
        var bytes = unicode ? Encoding.Unicode.GetBytes(argument + "\0") : Encoding.UTF8.GetBytes(argument + "\0");
        var remote = VirtualAllocEx(process, IntPtr.Zero, (nuint)bytes.Length, MemCommitReserve, PageReadWrite);
        if (remote == IntPtr.Zero) throw new ConnectorException(errorCode);
        try
        {
            if (!WriteProcessMemory(process, remote, bytes, (nuint)bytes.Length, out var written) || written != (nuint)bytes.Length)
                throw new ConnectorException(errorCode);
            var thread = CreateRemoteThread(process, IntPtr.Zero, 0, entry, remote, 0, IntPtr.Zero);
            if (thread == IntPtr.Zero) throw new ConnectorException(errorCode);
            try
            {
                if (WaitForSingleObject(thread, InfiniteTimeoutGuardMs) != 0 ||
                    !GetExitCodeThread(thread, out var exitCode) || exitCode != 0)
                    throw new ConnectorException(errorCode);
            }
            finally { CloseHandle(thread); }
        }
        finally { VirtualFreeEx(process, remote, 0, MemRelease); }
    }

    private static ProcessModule? FindModule(Process process, string name)
    {
        try { return process.Modules.Cast<ProcessModule>().FirstOrDefault(module =>
            string.Equals(module.ModuleName, name, StringComparison.OrdinalIgnoreCase)); }
        catch (Exception error) when (error is InvalidOperationException or System.ComponentModel.Win32Exception)
        { throw new ConnectorException("vismockup_native_bridge_module_inventory_failed"); }
    }

    private static void VerifyHash(string path, string expected, string errorCode)
    {
        if (!File.Exists(path)) throw new ConnectorException(errorCode);
        using var stream = File.OpenRead(path);
        if (!string.Equals(Convert.ToHexString(SHA256.HashData(stream)), expected, StringComparison.OrdinalIgnoreCase))
            throw new ConnectorException(errorCode);
    }

    private static string NormalizeCode(string? value) => string.IsNullOrWhiteSpace(value) ? "response_invalid" :
        new string(value.Where(character => char.IsAsciiLetterOrDigit(character) || character == '_').ToArray()).ToLowerInvariant();
    private static void TryDelete(string path) { try { File.Delete(path); } catch (IOException) { } catch (UnauthorizedAccessException) { } }

    private sealed record BridgeResponse(string? Status, string? SourceIdentity, int TotalHierarchies,
        LiveHierarchyInventoryBridgeItem[]? Hierarchies);
    private sealed record LiveHierarchyInventoryBridgeItem(int NativeIndex, string? Name, bool Complete,
        LiveHierarchyInventoryNode[]? Nodes);

    [DllImport("kernel32.dll", SetLastError=true)] private static extern IntPtr OpenProcess(uint access, bool inherit, int processId);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern IntPtr VirtualAllocEx(IntPtr process, IntPtr address, nuint size, uint allocationType, uint protect);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern bool VirtualFreeEx(IntPtr process, IntPtr address, nuint size, uint freeType);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern bool WriteProcessMemory(IntPtr process, IntPtr address, byte[] buffer, nuint size, out nuint written);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern IntPtr CreateRemoteThread(IntPtr process, IntPtr attributes, nuint stackSize, IntPtr start, IntPtr parameter, uint flags, IntPtr threadId);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern bool GetExitCodeThread(IntPtr thread, out uint exitCode);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] private static extern IntPtr LoadLibraryExW(string path, IntPtr file, uint flags);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] private static extern IntPtr GetModuleHandleW(string name);
    [DllImport("kernel32.dll", CharSet=CharSet.Ansi, SetLastError=true)] private static extern IntPtr GetProcAddress(IntPtr module, string name);
    [DllImport("kernel32.dll", SetLastError=true)] private static extern bool FreeLibrary(IntPtr module);
}
