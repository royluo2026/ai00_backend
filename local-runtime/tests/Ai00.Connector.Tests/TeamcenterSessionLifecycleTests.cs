using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Ai00.Connector.AppHost;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class TeamcenterSessionLifecycleTests
{
    private static JsonElement Payload => JsonSerializer.SerializeToElement(new {
        source_selector=new TeamcenterSourceSelector("tc-production","uid","","","Latest Working","2026-09-22T00:00:00Z"),
        expected_visdoc_uid="uid" });
    internal sealed class Worker : ITeamcenterWorker, ITeamcenterVisualizationLifecycle
    {
        public bool Ready;
        public bool RejectLogin;
        public long Generation;
        public int Starts,Validations;
        public readonly TaskCompletionSource Entered=new(TaskCreationOptions.RunContinuationsAsynchronously);
        public readonly TaskCompletionSource Release=new(TaskCreationOptions.RunContinuationsAsynchronously);
        public CancellationToken ConsumerToken;
        internal ITeamcenterVisualizationLifecycle? Lifecycle;
        public bool IsReady(long generation)=>Lifecycle?.IsReady(generation)??(Ready&&generation==Generation);
        public Task StartAsync(long generation,string endpointId,string username,string password,CancellationToken ct)
        {ct.ThrowIfCancellationRequested();if(RejectLogin)throw new ConnectorException("teamcenter_authentication_failed");Generation=generation;Ready=true;Starts++;return Lifecycle?.StartAsync(generation,endpointId,username,password,ct)??Task.CompletedTask;}
        public void Invalidate(long generation){if(generation==Generation)Ready=false;Lifecycle?.Invalidate(generation);}
        public Task StopAsync(long generation,CancellationToken ct){Invalidate(generation);return Lifecycle?.StopAsync(generation,ct)??Task.CompletedTask;}
        public Task ValidateCredentialsAsync(string endpointId,string username,string password,CancellationToken ct){Validations++;return Task.CompletedTask;}
        public Task<IReadOnlyList<string>> GetRevisionRulesAsync(string username,string password,CancellationToken ct)=>Task.FromResult<IReadOnlyList<string>>([username+":"+password]);
        public Task<TeamcenterProductSearchResult> SearchAsync(string itemId,string revisionId,string revisionRule,string configurationDate,string username,string password,CancellationToken ct)=>throw new NotSupportedException();
        public Task<IReadOnlyList<TeamcenterOccurrence>> ObserveAsync(TeamcenterSourceSelector selector,int maxNodes,int maxDepth,string projection,string username,string password,CancellationToken ct)=>throw new NotSupportedException();
        public Task<TeamcenterLaunchResult> LaunchAsync(TeamcenterSourceSelector selector,string expected,string username,string password,CancellationToken ct)=>throw new NotSupportedException();
        public async Task<TeamcenterLaunchResult> ConsumeVisualizationAsync(TeamcenterSourceSelector selector,string expected,string operation,Func<string,CancellationToken,Task> consumer,string username,string password,CancellationToken ct)
        {
            ConsumerToken=ct;Entered.TrySetResult();await Release.Task; // deliberately ignores cancellation: late native completion
            return new("tclaunch:"+new string('a',64),true,expected,selector.IdentityHash);
        }
    }
    [Fact]
    public async Task Host_registration_owns_runtime_disposal()
    {
        using var h=new Harness();var services=new ServiceCollection();
        Program.RegisterTeamcenterRuntime(services,h.Runtime);
        var provider=services.BuildServiceProvider();
        Assert.Same(h.Runtime,provider.GetRequiredService<TeamcenterReadOnlyRuntime>());
        await h.Runtime.LoginAsync("tc-production","u","p",default);
        provider.Dispose();
        Assert.False(h.Worker.Ready);Assert.Equal("logged_out",h.Runtime.GetSessionStatus().State);
    }
    private sealed class Harness : IDisposable
    {
        public readonly string Root=Path.Combine(Path.GetTempPath(),"ai00-lifecycle-"+Guid.NewGuid().ToString("N"));
        public readonly Worker Worker=new();
        public readonly TeamcenterReadOnlyRuntime Runtime;
        public Harness(){Runtime=new(Worker,Path.Combine(Root,"cache.db"));}
        public void Dispose(){Runtime.Dispose();if(Directory.Exists(Root))Directory.Delete(Root,true);}
    }
    [Fact]
    public async Task Login_authenticates_persistent_worker_not_throwaway_validation()
    {
        using var h=new Harness();await h.Runtime.LoginAsync("tc-production","user","secret",default);
        Assert.Equal("ready",h.Runtime.GetSessionStatus().State);Assert.Equal(1,h.Worker.Starts);Assert.Equal(0,h.Worker.Validations);
        var rules=(TeamcenterRevisionRulesResult)await h.Runtime.GetRevisionRulesAsync(JsonSerializer.SerializeToElement(new{endpoint_id="tc-production"}),default);
        Assert.Equal("user:secret",Assert.Single(rules.Rules));
        h.Worker.Ready=false;Assert.Equal("logged_out",h.Runtime.GetSessionStatus().State);
        await h.Runtime.LoginAsync("tc-production","other","secret",default);Assert.Equal(2,h.Worker.Starts);
    }

    [Fact]
    public async Task Remembered_test_login_reauthenticates_after_restart_and_logout_removes_it()
    {
        var root=Path.Combine(Path.GetTempPath(),"ai00-remember-tc-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var store=new TeamcenterRememberedLoginStore(root);
            using(var first=new TeamcenterReadOnlyRuntime(new Worker(),Path.Combine(root,"first.db"),store))
                await first.LoginAsync("tc-production","user","secret",default,remember:true);
            Assert.DoesNotContain("secret",File.ReadAllText(Path.Combine(root,"teamcenter-login.v1.dpapi")));
            var worker=new Worker();
            using(var second=new TeamcenterReadOnlyRuntime(worker,Path.Combine(root,"second.db"),store))
            {
                Assert.Equal("logged_out",second.GetSessionStatus().State);
                Assert.True(await second.RestoreRememberedLoginAsync(default));
                Assert.Equal("ready",second.GetSessionStatus().State);
                Assert.Equal(1,worker.Starts);
                await second.LogoutAsync(default);
            }
            using(var third=new TeamcenterReadOnlyRuntime(new Worker(),Path.Combine(root,"third.db"),store))
                Assert.False(await third.RestoreRememberedLoginAsync(default));
        }
        finally {Directory.Delete(root,true);}
    }

    [Fact]
    public async Task Failed_remembered_authentication_drops_saved_credentials()
    {
        var root=Path.Combine(Path.GetTempPath(),"ai00-remember-tc-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var store=new TeamcenterRememberedLoginStore(root);
            using(var first=new TeamcenterReadOnlyRuntime(new Worker(),Path.Combine(root,"first.db"),store))
                await first.LoginAsync("tc-production","user","bad",default,remember:true);
            using(var second=new TeamcenterReadOnlyRuntime(new Worker{RejectLogin=true},Path.Combine(root,"second.db"),store))
                Assert.False(await second.RestoreRememberedLoginAsync(default));
            Assert.False(File.Exists(Path.Combine(root,"teamcenter-login.v1.dpapi")));
        }
        finally {Directory.Delete(root,true);}
    }
    [Theory]
    [InlineData(false)][InlineData(true)]
    public async Task Logout_or_account_switch_revokes_before_waiting_and_fences_late_result(bool switchAccount)
    {
        using var h=new Harness();await h.Runtime.LoginAsync("tc-production","user","secret",default);
        var consume=h.Runtime.ConsumeVisualizationAsync(Payload,"Open",(p,c)=>Task.CompletedTask,default);
        await h.Worker.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
        var transition=switchAccount?h.Runtime.LoginAsync("tc-production","other","secret",default):h.Runtime.LogoutAsync(default);
        try
        {
            Assert.Equal("logged_out",h.Runtime.GetSessionStatus().State);
            Assert.True(h.Worker.ConsumerToken.IsCancellationRequested);
            Assert.False(h.Worker.Ready);
        }
        finally{h.Worker.Release.TrySetResult();}
        await Assert.ThrowsAnyAsync<Exception>(()=>consume);
        await transition.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.Equal(switchAccount?"ready":"logged_out",h.Runtime.GetSessionStatus().State);
    }
    [Fact]
    public async Task Dispose_fences_active_and_queued_calls_without_disposing_their_gate()
    {
        using var h=new Harness();await h.Runtime.LoginAsync("tc-production","user","secret",default);
        var first=h.Runtime.ConsumeVisualizationAsync(Payload,"Open",(p,c)=>Task.CompletedTask,default);
        await h.Worker.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
        var queued=h.Runtime.ConsumeVisualizationAsync(Payload,"Open",(p,c)=>Task.CompletedTask,default);
        h.Runtime.Dispose();h.Worker.Release.TrySetResult();
        await Assert.ThrowsAnyAsync<Exception>(()=>first);
        var queuedError=await Assert.ThrowsAnyAsync<Exception>(()=>queued.WaitAsync(TimeSpan.FromSeconds(2)));
        Assert.IsNotType<TimeoutException>(queuedError);
        Assert.Equal("logged_out",h.Runtime.GetSessionStatus().State);
    }
}
