using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.AppHost;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public class ViewerDocumentPreparationTests
{
    [Fact]
    public void StableActiveDocumentAndUniqueMdiChildCanBePinned()
    {
        var documents=new Queue<string>(["doc-A","doc-A"]);
        var properties=new Dictionary<nint,nint>();
        var target=NativeDocumentWindow.CaptureActiveCore(123,"doc-A",()=>documents.Dequeue(),
            _=>[(nint)41],(window,pid)=>window==41&&pid==123,
            (window,name)=>properties.GetValueOrDefault(window),
            (window,name,value)=>{properties[window]=value;return true;},null);

        Assert.Equal("41",target.DocumentWindow);
        Assert.NotEqual("0",target.WindowToken);
        Assert.Equal((nint)long.Parse(target.WindowToken),properties[(nint)41]);
    }

    [Fact]
    public void ExistingWindowIsSelectedByComDocumentIdNotItsTitle()
    {
        var active=(nint)41;
        var properties=new Dictionary<nint,nint>();
        var target=NativeDocumentWindow.FindAndCaptureCore(123,"W10",()=>active==42?"W10":"bolt",
            _=>[(nint)41,(nint)42],(window,pid)=>pid==123&&window is 41 or 42,
            window=>{active=window;return active;},()=>active,
            (window,name)=>properties.GetValueOrDefault(window),
            (window,name,value)=>{properties[window]=value;return true;});

        Assert.Equal("42",target.DocumentWindow);
        Assert.Equal((nint)42,active);
        Assert.Equal((nint)long.Parse(target.WindowToken),properties[(nint)42]);
    }

    [Fact]
    public void MissingExistingWindowRestoresPreviouslyActiveDocument()
    {
        var active=(nint)41;
        var error=Assert.Throws<ConnectorNoEffectException>(()=>NativeDocumentWindow.FindAndCaptureCore(
            123,"W10",()=>"bolt",_=>[(nint)41,(nint)42],(_,_)=>true,
            window=>{active=window;return active;},()=>active,(_,_)=>0,(_,_,_)=>true));
        Assert.Equal("document_session_changed",error.Code);
        Assert.Equal((nint)41,active);
    }

    [Fact]
    public async Task ExistingIdentitySelectsBoundSessionWithoutOpeningAnotherModel()
    {
        using var sta=new StaDispatcher();
        var bolt=new FakeDocument("bolt","tc://bolt",FakeNode.FlatTree(1));
        var w10=new FakeDocument("W10","tc://w10",FakeNode.FlatTree(1));
        var app=new FakeApplication("14.2",bolt){OpenDocuments=[bolt,w10]};
        w10.AfterNativeActivation=()=>app.ActiveDocument=w10;
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([Path.GetTempPath()]),
            new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456});
        var expected=CanonicalJson.Hash(new{process_id=123,process_started_utc_ticks="456",document_handle="W10"});
        var method=typeof(VisMockupAdapter).GetMethod("ReadExistingDocumentIdentityAsync",
            System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.NonPublic);
        Assert.NotNull(method);

        var result=await (Task<object>)method!.Invoke(adapter,[JsonSerializer.SerializeToElement(new{
            expected_document_session=expected}),CancellationToken.None])!;

        Assert.Equal(expected,JsonSerializer.SerializeToElement(result).GetProperty("document_session").GetString());
        Assert.Same(w10,app.ActiveDocument);
        Assert.Equal(0,app.OpenCalls);
    }

    [Theory]
    [InlineData("doc-A","doc-B")]
    [InlineData("doc-B","doc-B")]
    public void ChangedActiveDocumentCannotBePinned(string before,string after)
    {
        var documents=new Queue<string>([before,after]);
        var error=Assert.Throws<ConnectorNoEffectException>(()=>NativeDocumentWindow.CaptureActiveCore(
            123,"doc-A",()=>documents.Dequeue(),_=>[(nint)41],(_,_)=>true,(_,_)=>0,(_,_,_)=>true,null));
        Assert.Equal("document_session_changed",error.Code);
    }

    [Fact]
    public void MultipleMdiContainersOrForeignPidCannotBePinned()
    {
        NativeDocumentWindow Capture(IReadOnlyList<nint> active,Func<nint,int,bool> owned)
        {
            var documents=new Queue<string>(["doc-A","doc-A"]);
            return NativeDocumentWindow.CaptureActiveCore(123,"doc-A",()=>documents.Dequeue(),_=>active,
                owned,(_,_)=>0,(_,_,_)=>true,null);
        }

        Assert.Equal("vismockup_document_window_unavailable",
            Assert.Throws<ConnectorException>(()=>Capture([(nint)41,(nint)42],(_,_)=>true)).Code);
        Assert.Equal("vismockup_document_window_unavailable",
            Assert.Throws<ConnectorException>(()=>Capture([(nint)41],(_,_)=>false)).Code);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(67891)]
    public void MissingOrReplacedMarkerRejectsActivation(long actualMarker)
    {
        var target=new NativeDocumentWindow("41","67890");
        var error=Assert.Throws<ConnectorException>(()=>NativeDocumentWindow.ActivateCore(123,"doc-A",
            ()=>"doc-A",target,(window,pid)=>window==41&&pid==123,(_,_)=>(nint)actualMarker,_=>41));
        Assert.Equal("vismockup_document_window_changed",error.Code);
    }

    [Fact]
    public void HwndReuseWithOldMarkerCannotBeActivated()
    {
        var target=new NativeDocumentWindow("41","67890");
        var error=Assert.Throws<ConnectorException>(()=>NativeDocumentWindow.ActivateCore(123,"doc-A",
            ()=>"doc-A",target,(_,_)=>false,(_,_)=>67890,_=>41));
        Assert.Equal("vismockup_document_window_changed",error.Code);
    }

    [Fact]
    public void ExactMarkedWindowActivatesOnlyWhenDocumentAndMdiReadbackStayStable()
    {
        var documents=new Queue<string>(["doc-A","doc-A"]);
        var target=new NativeDocumentWindow("41","67890");
        var activated=NativeDocumentWindow.ActivateCore(123,"doc-A",()=>documents.Dequeue(),target,
            (window,pid)=>window==41&&pid==123,(_,_)=>67890,_=>41);
        Assert.Equal(target,activated);

        documents=new Queue<string>(["doc-A","doc-B"]);
        var error=Assert.Throws<ConnectorNoEffectException>(()=>NativeDocumentWindow.ActivateCore(
            123,"doc-A",()=>documents.Dequeue(),target,(_,_)=>true,(_,_)=>67890,_=>41));
        Assert.Equal("document_session_changed",error.Code);
    }
    [Fact]
    public void PreparationAcceptsOnlyAnInstalledInteractionNotCallerIdentity()
    {
        var json="""{"type":"prepare_document","request_id":"prepare","interaction_id":"session"}""";
        Assert.Equal("prepare_document", ViewerInteractionProtocol.ParseRequest(json).Type);
        Assert.ThrowsAny<Exception>(()=>ViewerInteractionProtocol.ParseRequest(json.Replace("\"type\":", "\"process_id\":123,\"type\":")));
        var activate="""{"type":"activate_document","request_id":"activate","interaction_id":"session"}""";
        Assert.Equal("activate_document",ViewerInteractionProtocol.ParseRequest(activate).Type);
        Assert.ThrowsAny<Exception>(()=>ViewerInteractionProtocol.ParseRequest(activate.Replace("\"type\":", "\"document_window\":41,\"type\":")));
    }

    [Fact]
    public async Task PreparedDocumentsAreActivatedFromAProcessLocalSessionCacheWithoutOpening()
    {
        using var sta=new StaDispatcher();
        var a=new FakeDocument("A","tc://a",FakeNode.FlatTree(1)){NativeWindow=new("41","401")};
        var b=new FakeDocument("B","tc://b",FakeNode.FlatTree(1)){NativeWindow=new("42","402")};
        var app=new FakeApplication("14.2",a){OpenDocuments=[a,b]};
        a.AfterNativeActivation=()=>app.ActiveDocument=a;
        b.AfterNativeActivation=()=>app.ActiveDocument=b;
        var com=new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456};
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([Path.GetTempPath()]),com);
        var sessionA=CanonicalJson.Hash(new{process_id=123,process_started_utc_ticks="456",document_handle="A"});
        var prepared=await adapter.PrepareViewerDocumentAsync(sessionA,CancellationToken.None);
        app.ActiveDocument=b;

        var activated=await adapter.ActivateViewerDocumentAsync(sessionA,CancellationToken.None);

        Assert.Equal("A",activated.DocumentId);
        Assert.Equal(prepared,activated);
        Assert.Same(a,app.ActiveDocument);
        Assert.Equal(0,app.OpenCalls);
        Assert.Equal(1,a.ActivateNativeWindowCalls);
    }

    [Theory]
    [InlineData("unknown")]
    [InlineData("process-reuse")]
    [InlineData("closed")]
    [InlineData("cancelled")]
    public async Task InvalidPreparedDocumentCannotBeActivated(string scenario)
    {
        using var sta=new StaDispatcher();
        var a=new FakeDocument("A","tc://a",FakeNode.FlatTree(1)){NativeWindow=new("41","401")};
        var b=new FakeDocument("B","tc://b",FakeNode.FlatTree(1)){NativeWindow=new("42","402")};
        var app=new FakeApplication("14.2",a){OpenDocuments=[a,b]};
        a.AfterNativeActivation=()=>app.ActiveDocument=a;
        var com=new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456};
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([Path.GetTempPath()]),com);
        var sessionA=CanonicalJson.Hash(new{process_id=123,process_started_utc_ticks="456",document_handle="A"});
        await adapter.PrepareViewerDocumentAsync(sessionA,CancellationToken.None);
        app.ActiveDocument=b;
        if(scenario=="process-reuse")com.ProcessStartUtcTicks=789;
        if(scenario=="closed")app.OpenDocuments=[b];
        using var cancel=new CancellationTokenSource();
        if(scenario=="cancelled")cancel.Cancel();

        Task Act()=>adapter.ActivateViewerDocumentAsync(scenario=="unknown"?"sha256:"+new string('0',64):sessionA,cancel.Token);
        if(scenario=="cancelled")await Assert.ThrowsAnyAsync<OperationCanceledException>(Act);
        else Assert.Equal(scenario=="closed"?"document_closed":"document_session_changed",(await Assert.ThrowsAsync<ConnectorNoEffectException>(Act)).Code);
        Assert.Equal(0,app.OpenCalls);
    }

    [Theory]
    [InlineData("process_changed")]
    [InlineData("enumeration_failed")]
    [InlineData("duplicate_handle")]
    public async Task AmbiguousAbsenceNeverReportsDocumentClosed(string scenario)
    {
        using var sta=new StaDispatcher();
        var document=new FakeDocument("A","cache.plmxml",FakeNode.FlatTree(1)){NativeWindow=new("41","401")};
        var original=new FakeApplication("14.2",document);
        var application=new ObservedApplication(original);
        var com=new FakeVisMockupCom{ExistingApplication=application,ProcessId=123,ProcessStartUtcTicks=456};
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([Path.GetTempPath()]),com);
        var session=CanonicalJson.Hash(new{process_id=123,process_started_utc_ticks="456",document_handle="A"});
        await adapter.PrepareViewerDocumentAsync(session,default);
        application.ReadDocuments=()=>
        {
            if(scenario=="enumeration_failed")throw new InvalidOperationException("enumeration_failed");
            if(scenario=="duplicate_handle")return new IVisMockupDocument[]{document,document};
            com.ProcessStartUtcTicks=789;return Array.Empty<IVisMockupDocument>();
        };
        var error=await Assert.ThrowsAnyAsync<Exception>(()=>adapter.ActivateViewerDocumentAsync(session,default));
        Assert.False(error is ConnectorException connector && connector.Code=="document_closed");
        Assert.Equal(0,original.OpenCalls);
    }

    private sealed class ObservedApplication(FakeApplication inner):IVisMockupApplication
    {
        public Func<IReadOnlyList<IVisMockupDocument>>? ReadDocuments;
        public string ProductVersion=>inner.ProductVersion;
        public IVisMockupDocument? ActiveDocument=>inner.ActiveDocument;
        public IReadOnlyList<IVisMockupDocument> OpenDocuments=>ReadDocuments?.Invoke()??inner.OpenDocuments;
        public IVisMockupDocument OpenDocument(string path)=>inner.OpenDocument(path);
        public void CloseAllDocuments()=>inner.CloseAllDocuments();
    }

    [Theory]
    [InlineData("valid")]
    [InlineData("document-switch")]
    [InlineData("process-reuse")]
    [InlineData("cancelled")]
    public async Task PreparationUsesExactNativeSessionWithoutOpening(string scenario)
    {
        using var sta=new StaDispatcher();
        var document=new FakeDocument("doc", "tc://part", null!);
        var app=new FakeApplication("14.2",document);
        var com=new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456};
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([Path.GetTempPath()]),com);
        var expected=CanonicalJson.Hash(new{process_id=123,process_started_utc_ticks="456",document_handle="doc"});
        if(scenario=="document-switch")app.ActiveDocument=new FakeDocument("other","tc://part",null!);
        if(scenario=="process-reuse")com.ProcessStartUtcTicks=789;
        using var cancel=new CancellationTokenSource();
        if(scenario=="cancelled")cancel.Cancel();
        // Reflection makes RED a behavior assertion instead of a compilation failure.
        var method=typeof(VisMockupAdapter).GetMethod("PrepareViewerDocumentAsync");
        Assert.NotNull(method);
        async Task<JsonElement> Prepare()
        {
            var task=(Task)method!.Invoke(adapter,[expected,cancel.Token])!;
            await task;
            return JsonSerializer.SerializeToElement(task.GetType().GetProperty("Result")!.GetValue(task));
        }
        if(scenario=="valid")
        {
            var result=await Prepare();
            Assert.Equal(123,result.GetProperty("ProcessId").GetInt32());
            Assert.Equal("doc",result.GetProperty("DocumentId").GetString());
            Assert.Equal(expected,result.GetProperty("DocumentSession").GetString());
            Assert.Equal("12345",result.GetProperty("DocumentWindow").GetString());
            Assert.Equal("67890",result.GetProperty("WindowToken").GetString());
        }
        else if(scenario=="cancelled")await Assert.ThrowsAnyAsync<OperationCanceledException>(Prepare);
        else
        {
            var error=await Assert.ThrowsAsync<ConnectorNoEffectException>(Prepare);
            Assert.Equal("document_session_changed",error.Code);
        }
        Assert.Null(app.LastOpenedDocument);
        Assert.Equal(0,document.InsertDocumentCalls);
    }

    [Fact]
    public async Task PreparationReadsTheActiveDocumentOnlyOnceBeforeAndAfterPinning()
    {
        using var sta=new StaDispatcher();
        var document=new FakeDocument("doc", "tc://part", null!);
        var app=new FakeApplication("14.2",document);
        var com=new FakeVisMockupCom{ExistingApplication=app,ProcessId=123,ProcessStartUtcTicks=456};
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([Path.GetTempPath()]),com);
        var expected=CanonicalJson.Hash(new{process_id=123,process_started_utc_ticks="456",document_handle="doc"});

        await adapter.PrepareViewerDocumentAsync(expected,CancellationToken.None);

        Assert.Equal(2,app.ActiveDocumentReads);
    }

    [Fact]
    public void ColdDocumentPreparationAndNodeMappingHaveSeparateBoundedBudgets()
    {
        var method=typeof(ViewerInteractionPipeHost).GetMethod("InteractionTimeout",
            System.Reflection.BindingFlags.Static|System.Reflection.BindingFlags.NonPublic|System.Reflection.BindingFlags.Public);
        Assert.NotNull(method);
        TimeSpan Budget(string type)=>(TimeSpan)method!.Invoke(null,[type])!;
        Assert.Equal(TimeSpan.FromSeconds(15),Budget("prepare_document"));
        Assert.Equal(TimeSpan.FromSeconds(15),Budget("activate_document"));
        Assert.Equal(TimeSpan.FromSeconds(25),Budget("resolve_nodes"));
    }
}
