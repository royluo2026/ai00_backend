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
            var startupClock=System.Diagnostics.Stopwatch.StartNew();
            void StartupStage(string stage)
            {
#if DEBUG
                Console.Error.WriteLine($"[ConnectorHost] startup {stage}: {startupClock.ElapsedMilliseconds}ms");
#endif
            }
            if(!OperatingSystem.IsWindows()||!Environment.Is64BitProcess)throw new PlatformNotSupportedException("windows_x64_required");
            var options=AppHostOptions.Parse(args);
            var verified=HostManifest.Verify(options);using var parent=verified.Parent;
            // The App-owned test host has its own identity, journal and cache. It
            // never consumes state from the separately installed Connector service.
            var root=StateRoot(options.Development);
            var stateSuffix=options.Development?".test":"";
            using var key=new DeviceSigningKeyStore(root).GetOrCreate();
            var security=new DirectorySecurity();var sid=WindowsIdentity.GetCurrent().User!;
            security.SetAccessRuleProtection(true,false);security.SetOwner(sid);
            security.AddAccessRule(new FileSystemAccessRule(sid,FileSystemRights.FullControl,InheritanceFlags.ContainerInherit|InheritanceFlags.ObjectInherit,PropagationFlags.None,AccessControlType.Allow));
            new DirectoryInfo(root).SetAccessControl(security);
            using var singleton=new FileStream(Path.Combine(root,$"host{stateSuffix}.lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);
            using var sta=new StaDispatcher();
            var com=new BreakawayVisMockupCom(verified.Manifest.VisMockupExecutable,verified.Manifest.VisMockupPublisher);
            var reconnected=await sta.InvokeAsync(com.TryReconnectExistingApplication);
            Console.Error.WriteLine($"AI00_VISMOCKUP_STARTUP_RECONNECT:{reconnected}");
            var teamcenter=TeamcenterReadOnlyRuntime.CreateInstalled(root,options.Development);
            StartupStage("teamcenter");
            var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([Path.Combine(root,"artifacts")]),com,
                Path.Combine(root,"captures"),Path.Combine(root,$"vismockup-tree-cache{stateSuffix}.db"),teamcenter);
            using var http=new HttpClient(new HttpClientHandler{AllowAutoRedirect=false,UseCookies=false}){Timeout=TimeSpan.FromSeconds(30)};
            // Large JT uploads retain the plan/session cancellation budget;
            // ordinary control requests and screenshots keep their short timeout.
            using var artifactHttp=new HttpClient(new HttpClientHandler{AllowAutoRedirect=false,UseCookies=false}){Timeout=TimeSpan.FromMinutes(10)};
            var builder=Host.CreateApplicationBuilder(new HostApplicationBuilderSettings{Args=[],DisableDefaults=true});
            builder.Logging.ClearProviders();
#if DEBUG
            if(options.Development)builder.Logging.AddSimpleConsole(settings=>settings.SingleLine=true);
#endif
            builder.Services.AddSingleton(options);builder.Services.AddSingleton(verified.Manifest);
            builder.Services.AddSingleton(new DiagnosticIdentity(options.ParentPid,Environment.ProcessId,Environment.ProcessPath!,verified.Manifest.Publisher,verified.Digest,options.LaunchNonce));
            builder.Services.AddSingleton<DiagnosticPipeHost>();
            builder.Services.AddHostedService(s=>s.GetRequiredService<DiagnosticPipeHost>());
            RegisterTeamcenterRuntime(builder.Services,teamcenter);
            builder.Services.AddSingleton<LocalOpenCancellation>();
            builder.Services.AddHostedService<TeamcenterControlPipeHost>();
            builder.Services.AddSingleton(new RuntimeTransport(http,options.GatewayOrigin,artifactHttp));
            builder.Services.AddSingleton<IAppArtifactMaterializer>(services=>new AppArtifactMaterializer(
                services.GetRequiredService<RuntimeTransport>(),Path.Combine(root,"artifacts")));
            builder.Services.AddSingleton<IAppCaptureUploader>(services=>new AppCaptureUploader(
                services.GetRequiredService<RuntimeTransport>(),Path.Combine(root,"captures"),Path.Combine(root,"teamcenter-model-files")));
            builder.Services.AddSingleton(key);builder.Services.AddSingleton(new AppCredentialStore(root,options.GatewayOrigin));
            builder.Services.AddSingleton(new AppPlanJournal(Path.Combine(root,$"execution{stateSuffix}.v2.journal")));
            StartupStage("journal");
            builder.Services.AddSingleton(adapter);builder.Services.AddSingleton(new PostConditionProbes(sta,com,adapter));
            var viewerGate=new ViewerExecutionGate();
            var viewerLog=new ViewerDiagnosticLog(Path.Combine(root,"logs","viewer-interaction.jsonl"));
            viewerLog.Write("runtime_started",new{development=options.Development});
            adapter.ViewerDiagnostic=viewerLog.Write;
            teamcenter.Diagnostic=viewerLog.Write;
            var viewerSession=new ViewerInteractionSession();
            var viewerContext=new ViewerInteractionRuntimeContext();
            var viewerJournal=new ViewerInteractionJournal(Path.Combine(root,$"viewer-interaction{stateSuffix}.v1.journal"));
            if(viewerJournal.HasUnknown)viewerGate.Quarantine("viewer_recovery_required");
            adapter.ViewerInteractionAdmissionAllowed=()=>!viewerGate.IsQuarantined&&viewerSession.IsDispatchAuthorized(
                viewerContext.Current,DateTimeOffset.UtcNow,ViewerInteractionPipeHost.MonotonicNow());
            builder.Services.AddSingleton(viewerGate);builder.Services.AddSingleton(viewerSession);
            builder.Services.AddSingleton(viewerContext);builder.Services.AddSingleton(viewerJournal);
            builder.Services.AddSingleton(new ViewerInteractionExecutor(viewerSession,viewerContext,viewerGate,viewerJournal,
                (operation,hash)=>adapter.Manifest.Supports(operation,hash),adapter.ExecuteViewerNodeAsync,diagnostic:viewerLog.Write));
            // Main owns the default-off UI feature flag. This channel cannot dispatch
            // until a server-signed grant is installed for the authenticated runtime.
            builder.Services.AddHostedService<ViewerInteractionPipeHost>();
            builder.Services.AddHostedService<ViewerInteractionAuditWorker>();
            builder.Services.AddHostedService<RuntimeSessionWorker>();
            using var host=builder.Build();
            using var monitorCancellation=new CancellationTokenSource();
            var monitor=MonitorParentAsync(parent,host.Services.GetRequiredService<IHostApplicationLifetime>(),monitorCancellation.Token);
            try{await host.RunAsync();}finally{monitorCancellation.Cancel();await monitor;}
            return 0;
        }
        catch(Exception error)
        {
            _ = error;
#if DEBUG
            Console.Error.WriteLine($"[ConnectorHost] {error.GetType().Name}: {error.Message}");
#endif
            return 1; // Release builds never emit launch secrets, credentials, signed plans or COM payloads.
        }
    }
    internal static void RegisterTeamcenterRuntime(IServiceCollection services,TeamcenterReadOnlyRuntime runtime)
        =>services.AddSingleton(_=>runtime); // factory registration transfers disposal ownership to the host
    internal static string StateRoot(bool development)=>Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "AI00","App",development?"Connector-Test":"Connector");
    private static async Task MonitorParentAsync(System.Diagnostics.Process parent,IHostApplicationLifetime lifetime,CancellationToken ct)
    {
        try{await parent.WaitForExitAsync(ct);lifetime.StopApplication();}catch(OperationCanceledException)when(ct.IsCancellationRequested){}
    }
}
