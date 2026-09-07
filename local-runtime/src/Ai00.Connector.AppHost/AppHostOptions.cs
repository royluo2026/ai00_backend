using System.Diagnostics;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Ai00.Connector.Adapters.VisMockup;

namespace Ai00.Connector.AppHost;

public sealed record AppHostOptions(int ParentPid, string PipeName, string LaunchNonce, string ManifestPath, Uri GatewayOrigin)
{
    public static AppHostOptions Parse(string[] args)
    {
        string[] names=["--parent-pid","--pipe-name","--launch-nonce","--manifest-path","--gateway-origin"];
        var values=new Dictionary<string,string>(StringComparer.Ordinal);
        if(args.Length!=10)throw new InvalidDataException("startup_arguments_invalid");
        for(var i=0;i<args.Length;i+=2)
            if(!names.Contains(args[i]) || !values.TryAdd(args[i],args[i+1]))throw new InvalidDataException("startup_arguments_invalid");
        if(!int.TryParse(values[names[0]],out var pid)||pid<=0)throw new InvalidDataException("parent_identity_invalid");
        if(!Regex.IsMatch(values[names[1]],"\\AAI00\\.Connector\\.[a-f0-9]{32}\\z"))throw new InvalidDataException("pipe_name_invalid");
        if(!Regex.IsMatch(values[names[2]],"\\A[a-f0-9]{64}\\z"))throw new InvalidDataException("launch_nonce_invalid");
        if(!Path.IsPathFullyQualified(values[names[3]])||values[names[3]].StartsWith("\\\\"))throw new InvalidDataException("manifest_path_invalid");
        var origin=new Uri(values[names[4]],UriKind.Absolute);
        if(origin.Scheme!="https"||origin.IsLoopback||origin.AbsolutePath!="/"||origin.UserInfo!=""||origin.Query!=""||origin.Fragment!="")throw new InvalidDataException("gateway_origin_invalid");
        return new(pid,values[names[1]],values[names[2]],Path.GetFullPath(values[names[3]]),origin);
    }
}

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record HostManifest(string Protocol,string HostVersion,string GatewayOrigin,string ParentExecutable,
    string HostExecutable,string HostSha256,string Publisher,string VisMockupExecutable,string VisMockupPublisher,
    Dictionary<string,TrustedPlanKey> PlanKeys)
{
    public static (HostManifest Manifest,string Digest,Process Parent) Verify(AppHostOptions options)
    {
        var bytes=File.ReadAllBytes(options.ManifestPath);
        if(bytes.Length>65536)throw new InvalidDataException("manifest_size_invalid");
        var manifest=JsonSerializer.Deserialize<HostManifest>(bytes)??throw new InvalidDataException("manifest_invalid");
        var hostPath=Environment.ProcessPath??throw new InvalidDataException("host_path_missing");
        using var certificate=ExecutableTrust.RequireSigned(hostPath);
        if(certificate.Thumbprint!=manifest.Publisher)throw new InvalidDataException("publisher_mismatch");
        using var rsa=certificate.GetRSAPublicKey()??throw new InvalidDataException("manifest_rsa_publisher_required");
        if(!rsa.VerifyData(bytes,File.ReadAllBytes(options.ManifestPath+".sig"),HashAlgorithmName.SHA256,RSASignaturePadding.Pss))throw new InvalidDataException("manifest_signature_invalid");
        var root=Path.GetDirectoryName(options.ManifestPath)!;
        string Installed(string relative)
        {
            var path=Path.GetFullPath(Path.Combine(root,relative));
            if(Path.IsPathFullyQualified(relative)||!path.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("installed_path_invalid");
            return path;
        }
        var parent=Process.GetProcessById(options.ParentPid);
        try
        {
            if(!string.Equals(parent.MainModule?.FileName,Installed(manifest.ParentExecutable),StringComparison.OrdinalIgnoreCase)||
               !string.Equals(hostPath,Installed(manifest.HostExecutable),StringComparison.OrdinalIgnoreCase)||
               NativeParent.GetParentPid()!=options.ParentPid||parent.StartTime.ToUniversalTime()>Process.GetCurrentProcess().StartTime.ToUniversalTime())throw new InvalidDataException("parent_identity_mismatch");
            using var parentCert=ExecutableTrust.RequireSigned(parent.MainModule!.FileName);
            if(parentCert.Thumbprint!=manifest.Publisher)throw new InvalidDataException("parent_signer_mismatch");
            if(manifest.Protocol!="ai00.connector.execution-plan.v2"||manifest.HostVersion!=typeof(HostManifest).Assembly.GetName().Version!.ToString(3))throw new InvalidDataException("host_version_mismatch");
            if(new Uri(manifest.GatewayOrigin)!=options.GatewayOrigin)throw new InvalidDataException("gateway_origin_mismatch");
            if(Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(hostPath))).ToLowerInvariant()!=manifest.HostSha256)throw new InvalidDataException("host_digest_mismatch");
            if(manifest.PlanKeys.Count==0)throw new InvalidDataException("plan_keys_missing");
            return(manifest,Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),parent);
        }
        catch{parent.Dispose();throw;}
    }
}
internal static class NativeParent
{
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    private struct BasicInfo { public IntPtr Reserved1,Peb,Reserved2,Reserved3,Pid,ParentPid; }
    [System.Runtime.InteropServices.DllImport("ntdll.dll")]
    private static extern int NtQueryInformationProcess(IntPtr process,int informationClass,ref BasicInfo info,int size,out int returned);
    internal static int GetParentPid(){var info=new BasicInfo();if(NtQueryInformationProcess(Process.GetCurrentProcess().Handle,0,ref info,System.Runtime.InteropServices.Marshal.SizeOf<BasicInfo>(),out _)!=0)throw new InvalidDataException("parent_query_failed");return info.ParentPid.ToInt32();}
}
