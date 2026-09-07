using System.Security.AccessControl;
using System.Security.Principal;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts.V2;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
namespace Ai00.Connector.AppHost;
public static class Program
{
    public static async Task<int> Main(string[] args)
    {
        try
        {
            if(!OperatingSystem.IsWindows()||!Environment.Is64BitProcess)throw new PlatformNotSupportedException("windows_x64_required");
            var options=AppHostOptions.Parse(args);
            var verified=HostManifest.Verify(options);using var parent=verified.Parent;
            var root=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"AI00","App","Connector");
            using var key=new DeviceSigningKeyStore(root).GetOrCreate();
            var security=new DirectorySecurity();var sid=WindowsIdentity.GetCurrent().User!;
            security.SetAccessRuleProtection(true,false);security.SetOwner(sid);
            security.AddAccessRule(new FileSystemAccessRule(sid,FileSystemRights.FullControl,InheritanceFlags.ContainerInherit|InheritanceFlags.ObjectInherit,PropagationFlags.None,AccessControlType.Allow));
            new DirectoryInfo(root).SetAccessControl(security);
            using var singleton=new FileStream(Path.Combine(root,"host.lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);
            using var sta=new StaDispatcher();
            var com=new BreakawayVisMockupCom(verified.Manifest.VisMockupExecutable,verified.Manifest.VisMockupPublisher);
            var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([Path.Combine(root,"artifacts")]),com,Path.Combine(root,"captures"));
            using var http=new HttpClient(new HttpClientHandler{AllowAutoRedirect=false,UseCookies=false}){Timeout=TimeSpan.FromSeconds(30)};
            var builder=Host.CreateApplicationBuilder(new HostApplicationBuilderSettings{Args=[],DisableDefaults=true});
            builder.Logging.ClearProviders();
            builder.Services.AddSingleton(options);builder.Services.AddSingleton(verified.Manifest);
            builder.Services.AddSingleton(new DiagnosticIdentity(options.ParentPid,Environment.ProcessId,Environment.ProcessPath!,verified.Manifest.Publisher,verified.Digest,options.LaunchNonce));
            builder.Services.AddSingleton<DiagnosticPipeHost>();
            builder.Services.AddHostedService(s=>s.GetRequiredService<DiagnosticPipeHost>());
            builder.Services.AddSingleton(new RuntimeTransport(http,options.GatewayOrigin));
            builder.Services.AddSingleton(key);builder.Services.AddSingleton(new AppCredentialStore(root,options.GatewayOrigin));
            builder.Services.AddSingleton(new AppPlanJournal(Path.Combine(root,"execution.v2.journal")));
            builder.Services.AddSingleton(adapter);builder.Services.AddSingleton(new PostConditionProbes(sta,com));
            builder.Services.AddHostedService<RuntimeSessionWorker>();
            using var host=builder.Build();
            using var monitorCancellation=new CancellationTokenSource();
            var monitor=MonitorParentAsync(parent,host.Services.GetRequiredService<IHostApplicationLifetime>(),monitorCancellation.Token);
            try{await host.RunAsync();}finally{monitorCancellation.Cancel();await monitor;}
            return 0;
        }
        catch{return 1;} // Never emit launch secrets, credentials, signed plans or COM payloads to parent/stderr.
    }
    private static async Task MonitorParentAsync(System.Diagnostics.Process parent,IHostApplicationLifetime lifetime,CancellationToken ct)
    {
        try{await parent.WaitForExitAsync(ct);lifetime.StopApplication();}catch(OperationCanceledException)when(ct.IsCancellationRequested){}
    }
}
