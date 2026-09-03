using System.ComponentModel;
using System.Runtime.InteropServices;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Service;

public enum PowerRequestType { SystemRequired = 0 }

public interface ISystemPowerGuard
{
    IDisposable Acquire(string planId);
}

public interface IPowerRequestNative
{
    nint Create(string reason);
    bool Set(nint handle, PowerRequestType type);
    bool Clear(nint handle, PowerRequestType type);
    void Close(nint handle);
}

public sealed class SystemPowerGuard(IPowerRequestNative native) : ISystemPowerGuard
{
    public IDisposable Acquire(string planId)
    {
        if (string.IsNullOrWhiteSpace(planId)) throw new ConnectorException("plan_identity_invalid");
        var handle = native.Create("AI00 Connector plan " + planId);
        if (handle == 0 || handle == -1) throw new Win32Exception("PowerCreateRequest failed");
        if (!native.Set(handle, PowerRequestType.SystemRequired))
        {
            native.Close(handle);
            throw new Win32Exception("PowerSetRequest failed");
        }
        return new PowerLease(handle, native);
    }

    private sealed class PowerLease(nint handle, IPowerRequestNative native) : IDisposable
    {
        private nint _handle = handle;
        public void Dispose()
        {
            var current = Interlocked.Exchange(ref _handle, 0);
            if (current == 0) return;
            native.Clear(current, PowerRequestType.SystemRequired);
            native.Close(current);
        }
    }
}

public sealed class WindowsPowerRequestNative : IPowerRequestNative
{
    private const uint ContextVersion = 0;
    private const uint SimpleString = 0x1;

    public nint Create(string reason)
    {
        var value = Marshal.StringToHGlobalUni(reason);
        try
        {
            var context = new ReasonContext { Version = ContextVersion, Flags = SimpleString, Reason = value };
            return PowerCreateRequest(ref context);
        }
        finally
        {
            Marshal.FreeHGlobal(value);
        }
    }

    public bool Set(nint handle, PowerRequestType type) => PowerSetRequest(handle, type);
    public bool Clear(nint handle, PowerRequestType type) => PowerClearRequest(handle, type);
    public void Close(nint handle) => CloseHandle(handle);

    [StructLayout(LayoutKind.Sequential)]
    private struct ReasonContext
    {
        public uint Version;
        public uint Flags;
        public nint Reason;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern nint PowerCreateRequest(ref ReasonContext context);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool PowerSetRequest(nint powerRequest, PowerRequestType requestType);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool PowerClearRequest(nint powerRequest, PowerRequestType requestType);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(nint handle);
}
