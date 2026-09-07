using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using Ai00.Connector.Contracts;
namespace Ai00.Connector.Adapters.VisMockup;

public static class ExecutableTrust
{
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]private struct TrustFile{public uint Size;[MarshalAs(UnmanagedType.LPWStr)]public string Path;public IntPtr File,Subject;}
    [StructLayout(LayoutKind.Sequential)]private struct TrustData{public uint Size;public IntPtr Policy,Client;public uint UI,Revocation,Choice;public IntPtr File;public uint StateAction;public IntPtr State,Url;public uint Flags,Context;public IntPtr Signature;}
    [DllImport("wintrust.dll",ExactSpelling=true)]private static extern int WinVerifyTrust(IntPtr window,ref Guid action,ref TrustData data);
    public static X509Certificate2 RequireSigned(string path)
    {
        if(!Path.IsPathFullyQualified(path)||path.StartsWith("\\\\")||!File.Exists(path))throw new ConnectorException("signed_executable_required");
        for(var p=path;p!=null;p=Path.GetDirectoryName(p))if((File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0)throw new ConnectorException("executable_reparse_forbidden");
        var file=new TrustFile{Size=(uint)Marshal.SizeOf<TrustFile>(),Path=path};
        var ptr=Marshal.AllocHGlobal(Marshal.SizeOf<TrustFile>());Marshal.StructureToPtr(file,ptr,false);
        var data=new TrustData{Size=(uint)Marshal.SizeOf<TrustData>(),UI=2,Revocation=1,Choice=1,File=ptr,StateAction=1,Flags=0x80};
        var action=new Guid("00AAC56B-CD44-11d0-8CC2-00C04FC295EE");
        try
        {
            if(WinVerifyTrust(new IntPtr(-1),ref action,ref data)!=0)throw new ConnectorException("executable_signature_invalid");
            return new X509Certificate2(X509Certificate.CreateFromSignedFile(path));
        }
        finally{data.StateAction=2;WinVerifyTrust(new IntPtr(-1),ref action,ref data);Marshal.DestroyStructure<TrustFile>(ptr);Marshal.FreeHGlobal(ptr);}
    }
}

public sealed class VisMockupBreakawayLauncher(string executable,string publisher)
{
    public const uint CreateBreakawayFromJob=0x01000000;
    [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]private struct StartupInfo{public int Size;public IntPtr Reserved,Desktop,Title;public uint X,Y,XSize,YSize,XChars,YChars,Fill,Flags;public ushort Show,ReservedSize;public IntPtr ReservedBytes,Input,Output,Error;}
    [StructLayout(LayoutKind.Sequential)]private struct ProcessInfo{public IntPtr Process,Thread;public uint Pid,Tid;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]private static extern bool CreateProcessW(string application,StringBuilder command,IntPtr processAttributes,IntPtr threadAttributes,bool inherit,uint flags,IntPtr environment,string directory,ref StartupInfo startup,out ProcessInfo process);
    [DllImport("kernel32.dll",SetLastError=true)]private static extern bool IsProcessInJob(IntPtr process,IntPtr job,out bool inJob);
    [DllImport("kernel32.dll")]private static extern bool CloseHandle(IntPtr handle);
    public void Launch()
    {
        var path=Path.GetFullPath(executable);
        var programFiles=Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles)+Path.DirectorySeparatorChar;
        if(!path.StartsWith(programFiles,StringComparison.OrdinalIgnoreCase))throw new ConnectorException("vismockup_install_path_forbidden");
        using var cert=ExecutableTrust.RequireSigned(path);
        if(cert.Thumbprint!=publisher)throw new ConnectorException("vismockup_signer_mismatch");
        var startup=new StartupInfo{Size=Marshal.SizeOf<StartupInfo>()};
        if(!CreateProcessW(path,new StringBuilder("\""+path+"\""),IntPtr.Zero,IntPtr.Zero,false,CreateBreakawayFromJob,IntPtr.Zero,Path.GetDirectoryName(path)!,ref startup,out var process))throw new Win32Exception(Marshal.GetLastWin32Error());
        try{if(!IsProcessInJob(process.Process,IntPtr.Zero,out var inJob)||inJob)throw new ConnectorException("vismockup_breakaway_unverified");}
        finally{CloseHandle(process.Thread);CloseHandle(process.Process);}
        // No process termination ownership is taken, even if post-launch verification fails.
    }
}
