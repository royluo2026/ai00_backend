using Ai00.Connector.AppHost;
using Ai00.Connector.Contracts;
using Ai00.Connector.Contracts.V2;
using Xunit;
namespace Ai00.Connector.Tests;
public sealed class ExecutionDeliveryBudgetTests
{
    private static readonly DateTimeOffset Now=DateTimeOffset.Parse("2026-09-07T01:03:00Z");
    [Theory]
    [InlineData(600,600,660,570)]
    [InlineData(600,660,600,570)]
    [InlineData(120,600,660,120)]
    [InlineData(120,100,660,70)]
    [InlineData(600,30,660,0)]
    public void Effective_execution_budget_preserves_delivery_window_and_shorter_step_timeout(int step,int lease,int session,int expected)
    {
        Assert.Equal(TimeSpan.FromSeconds(expected),PlanExecutionWorker.RemainingExecutionBudget(step,Now.AddSeconds(lease),Now.AddSeconds(session),Now));
    }
    [Theory]
    [InlineData(29)]
    [InlineData(30)]
    public async Task Short_lease_budget_is_reported_without_adapter_dispatch(int seconds)
    {
        var root=Path.Combine(Path.GetTempPath(),"delivery-budget-"+Guid.NewGuid().ToString("N"));
        try {
            using var key=new DeviceSigningKeyStore(root).GetOrCreate();
            var journal=new AppPlanJournal(Path.Combine(root,"journal"));
            var adapter=new OutcomeUnknownRecoveryTests.FakeAdapter(()=>Task.FromResult(new AdapterResult(true)));
            var materializer=new UnexpectedMaterializer();
            var worker=new PlanExecutionWorker(journal,adapter,key,"device-key-001",
                new Dictionary<string,TrustedPlanKey>{{"cloud-plan-key-2026-09",new(ProtocolV2VectorTests.Vector["plan_public_jwk"]!.ToJsonString(),Now.AddDays(-1),Now.AddDays(1),false)}},()=>Now,artifactMaterializer:materializer);
            var result=await worker.ExecuteAsync(OutcomeUnknownRecoveryTests.Lease() with{LeaseUntil=Now.AddSeconds(seconds)},OutcomeUnknownRecoveryTests.Session(),default);
            Assert.Equal(0,adapter.Calls);Assert.Equal(0,materializer.Calls);Assert.Equal("failed_without_effect",result.OverallStatus);
            Assert.Equal("execution_delivery_budget_exhausted",result.Steps[0].GetProperty("error_code").GetString());
            Assert.DoesNotContain(journal.Events,item=>item.Kind=="invocation_started");
        } finally {if(Directory.Exists(root))Directory.Delete(root,true);}
    }
    private sealed class UnexpectedMaterializer:IAppArtifactMaterializer
    {
        public int Calls;
        public Task<System.Text.Json.JsonElement> MaterializeAsync(string planId,string leaseId,ConnectorStepV2 step,RuntimeSession session,CancellationToken ct)
        {Calls++;throw new InvalidOperationException("must not materialize without delivery budget");}
    }
}
