using System.Diagnostics;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Ai00.Connector.AppHost;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class TeamcenterVisualizationSessionTests
{
    private static readonly TeamcenterSourceSelector Source = new("tc-production", "uid", "", "", "", "");
    private sealed class Harness : IAsyncDisposable
    {
        public readonly string Root = Path.Combine(Path.GetTempPath(), "ai00-warm-test-" + Guid.NewGuid().ToString("N"));
        public readonly TeamcenterVisualizationSession Session;
        public Process? Child;
        public int Starts;
        public Harness(string mode = "normal")
        {
            Session = new TeamcenterVisualizationSession(() =>
            {
                Starts++;
                var info = new ProcessStartInfo(@"C:\Program Files\nodejs\node.exe") { UseShellExecute=false,
                    CreateNoWindow=true, RedirectStandardInput=true, RedirectStandardOutput=true, RedirectStandardError=true,
                    StandardInputEncoding=TeamcenterProcessWorker.CreateStartInfo("java","script",[]).StandardInputEncoding };
                info.ArgumentList.Add(Path.Combine(AppContext.BaseDirectory,"teamcenter_visualization_child.cjs"));
                info.ArgumentList.Add(mode);
                Child = Process.Start(info)!; return Child;
            }, Root);
        }
        public async ValueTask DisposeAsync()
        {
            await Session.StopAsync(1,CancellationToken.None);
            if(Directory.Exists(Root))Directory.Delete(Root,true);
        }
    }

    [Fact]
    public async Task Two_consumes_share_process_and_do_not_wait_for_exit()
    {
        await using var h=new Harness();using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
        await h.Session.StartAsync(1,"tc-production","u","p",timeout.Token);
        var calls=0;
        foreach(var op in new[]{"Open","Insert"})
        {
            var result=await h.Session.ConsumeAsync(Source,"uid",op,(path,ct)=>{
                Assert.Equal("JT",File.ReadAllText(path));calls++;return Task.CompletedTask;
            },timeout.Token);
            Assert.EndsWith(calls.ToString().PadLeft(64,'0'),result.LaunchId);
            Assert.True(h.Session.IsReady(1));Assert.False(h.Child!.HasExited);
        }
        Assert.Equal(1,h.Starts);Assert.Equal(2,calls);
        Assert.Single(Directory.GetDirectories(h.Root)); // only retained render-cache
    }
    [Theory]
    [InlineData("oversize")][InlineData("duplicate")][InlineData("wrong-id")][InlineData("wrong-generation")]
    public async Task Invalid_login_frame_revokes_worker(string mode)
    {
        await using var h=new Harness(mode);using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
        await Assert.ThrowsAnyAsync<Exception>(()=>h.Session.StartAsync(1,"tc-production","u","p",timeout.Token));
        Assert.False(h.Session.IsReady(1));Assert.Equal(1,h.Starts);
    }
    [Theory]
    [InlineData("crash-before",0)][InlineData("crash-after",1)][InlineData("late",1)]
    public async Task Failure_never_replays_or_claims_no_effect_after_consumer(string mode,int expectedCalls)
    {
        await using var h=new Harness(mode);using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
        await h.Session.StartAsync(1,"tc-production","u","p",timeout.Token);var calls=0;
        var error=await Assert.ThrowsAnyAsync<Exception>(()=>h.Session.ConsumeAsync(Source,"uid","Open",(p,c)=>{calls++;return Task.CompletedTask;},timeout.Token));
        Assert.Equal(expectedCalls,calls);Assert.Equal(1,h.Starts);Assert.False(h.Session.IsReady(1));
        if(calls>0)Assert.IsNotType<ConnectorNoEffectException>(error);
    }
    [Fact]
    public async Task Noise_is_drained_without_leaking_secrets_or_unbounded_history()
    {
        await using var h=new Harness("noise");using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
        await h.Session.StartAsync(1,"tc-production","u","p",timeout.Token);
        await h.Session.ConsumeAsync(Source,"uid","Open",(p,c)=>Task.CompletedTask,timeout.Token);
        Assert.InRange(h.Session.Timings.Count,0,32);
        Assert.All(h.Session.Timings,line=>Assert.DoesNotContain("secret",line));
    }
    [Theory]
    [InlineData(false)][InlineData(true)]
    public async Task Cancellation_fences_session_without_replay(bool afterConsumer)
    {
        await using var h=new Harness(afterConsumer?"hang-after":"hang-before");
        using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
        await h.Session.StartAsync(1,"tc-production","u","p",timeout.Token);
        using var cancel=new CancellationTokenSource(TimeSpan.FromMilliseconds(250));var calls=0;
        await Assert.ThrowsAnyAsync<Exception>(()=>h.Session.ConsumeAsync(Source,"uid","Open",(p,c)=>{calls++;return Task.CompletedTask;},cancel.Token));
        Assert.Equal(afterConsumer?1:0,calls);Assert.False(h.Session.IsReady(1));Assert.Equal(1,h.Starts);
    }
    [Fact]
    public async Task Old_generation_stop_cannot_stop_new_worker()
    {
        await using var h=new Harness();using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
        await h.Session.StartAsync(1,"tc-production","u","p",timeout.Token);
        await h.Session.StopAsync(1,default);
        try
        {
            await h.Session.StartAsync(2,"tc-production","v","p",timeout.Token);
            await h.Session.StopAsync(1,default);
            Assert.True(h.Session.IsReady(2));Assert.False(h.Session.IsReady(1));
        }
        finally {await h.Session.StopAsync(2,default);}
    }
    [Fact]
    public async Task Unsolicited_frames_invalidate_and_terminate_owned_worker()
    {
        await using var h=new Harness("unsolicited");using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(10));
        try {await h.Session.StartAsync(1,"tc-production","u","p",timeout.Token);}catch(ConnectorException){}catch(OperationCanceledException){}
        await Task.Delay(100);
        Assert.False(h.Session.IsReady(1));
        try {await h.Child!.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(2));}
        catch(InvalidOperationException){} // owned process handle already cleaned
    }
    private sealed class QueuedContext : SynchronizationContext
    {
        public readonly Queue<(SendOrPostCallback,object?)> Calls=new();
        public override void Post(SendOrPostCallback d,object? state){Calls.Enqueue((d,state));}
    }
    [Fact]
    public async Task Host_disposal_kills_child_that_ignores_logout_within_bound()
    {
        await using var h=new Harness("ignore-logout");
        using var runtime=new TeamcenterReadOnlyRuntime(new TeamcenterSessionLifecycleTests.Worker{Lifecycle=h.Session},Path.Combine(h.Root,"tc.db"));
        var services=new ServiceCollection();Program.RegisterTeamcenterRuntime(services,runtime);
        var provider=services.BuildServiceProvider();provider.GetRequiredService<TeamcenterReadOnlyRuntime>();
        await runtime.LoginAsync("tc-production","u","p",default);
        using var watcher=Process.GetProcessById(h.Child!.Id);var started=Stopwatch.StartNew();
        provider.Dispose();
        Assert.True(watcher.HasExited);Assert.True(started.Elapsed<TimeSpan.FromSeconds(5));
        Assert.Equal("logged_out",runtime.GetSessionStatus().State);
    }
    [Fact]
    public async Task Teardown_does_not_need_callers_synchronization_context()
    {
        await using var h=new Harness();await h.Session.StartAsync(1,"tc-production","u","p",default);
        var previous=SynchronizationContext.Current;var blocked=new QueuedContext();Task stop;
        SynchronizationContext.SetSynchronizationContext(blocked);
        try {stop=h.Session.StopAsync(1,default);}
        finally{SynchronizationContext.SetSynchronizationContext(previous);}
        try {Assert.Empty(blocked.Calls);}
        finally {while(blocked.Calls.TryDequeue(out var call))call.Item1(call.Item2);await stop.WaitAsync(TimeSpan.FromSeconds(5));}
    }
}
