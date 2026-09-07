using System.Diagnostics;
using System.Security.AccessControl;
using System.Security.Principal;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Tray;

public static class SessionHostProcess
{
    public static bool EnsureStarted(Func<bool> isRunning, Action start)
    {
        if (isRunning()) return false;
        start();
        return true;
    }

    public static bool EnsureStarted(SessionHostStartRequest request)
    {
        PreparePresenceDirectory(request.WindowsSid);
        var sessionId = Process.GetCurrentProcess().SessionId;
        return EnsureStarted(
            () => Process.GetProcessesByName("Ai00.Connector.SessionHost")
                .Any(process => process.SessionId == sessionId),
            () =>
            {
                var startInfo = new ProcessStartInfo(
                    Path.Combine(AppContext.BaseDirectory, "Ai00.Connector.SessionHost.exe"))
                {
                    UseShellExecute = false,
                    CreateNoWindow = true,
                };
                startInfo.Environment["AI00_CONNECTOR_DEVICE_ID"] = request.DeviceId;
                startInfo.Environment["AI00_CONNECTOR_USER_ID"] = request.UserId;
                _ = Process.Start(startInfo)
                    ?? throw new InvalidOperationException("connector_session_host_start_failed");
            });
    }

    private static void PreparePresenceDirectory(string windowsSid)
    {
        var path = Path.GetDirectoryName(SessionHostPresencePath.For(windowsSid))!;
        Directory.CreateDirectory(path);
        var security = new DirectorySecurity();
        security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);
        security.AddAccessRule(new FileSystemAccessRule(
            WindowsIdentity.GetCurrent().User!, FileSystemRights.FullControl,
            InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
            PropagationFlags.None, AccessControlType.Allow));
        security.AddAccessRule(new FileSystemAccessRule(
            new SecurityIdentifier(WellKnownSidType.LocalServiceSid, null),
            FileSystemRights.ReadAndExecute,
            InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
            PropagationFlags.None, AccessControlType.Allow));
        security.AddAccessRule(new FileSystemAccessRule(
            new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null),
            FileSystemRights.FullControl,
            InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
            PropagationFlags.None, AccessControlType.Allow));
        new DirectoryInfo(path).SetAccessControl(security);
    }
}
