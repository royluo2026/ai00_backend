using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupDocumentLifecycleTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), "ai00-vismockup-lifecycle", Guid.NewGuid().ToString("N"));

    [Theory]
    [InlineData(1, 9)]
    [InlineData(2, 9)]
    [InlineData(1, 10)]
    [InlineData(2, 10)]
    public async Task Teamcenter_launch_versions_obey_document_capacity(int version, int count)
    {
        Directory.CreateDirectory(_directory);
        var app = new FakeApplication("14.2.0", null) { OpenDocuments = Enumerable.Range(0, count)
            .Select(index => (IVisMockupDocument)new FakeDocument($"doc-{index}", $"tc://other/{index}", FakeNode.FlatTree(1))).ToArray() };
        var worker = new OnlineMaterialTeamcenterWorker(Path.Combine(_directory, "limit.vvi"));
        using var runtime = new TeamcenterReadOnlyRuntime(worker, Path.Combine(_directory, "tc.db"));
        await runtime.LoginAsync("tc-production", "user", "secret", default);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = app, ProcessId = 123, ProcessStartUtcTicks = 456 },
            _directory, Path.Combine(_directory, "tree.db"), runtime);
        var operation = new AdapterOperation($"teamcenter.visualization.launch@{version}", OnlineSelectorPayload());
        if (count == 9) Assert.True((await adapter.ExecuteAsync(operation, default)).Ok);
        else Assert.Equal("vismockup_document_limit_exceeded", (await Assert.ThrowsAsync<ConnectorNoEffectException>(() =>
            adapter.ExecuteAsync(operation, default))).Code);
        Assert.Equal(count == 9 ? 1 : 0, app.OpenCalls);
        Assert.Equal(10, app.OpenDocuments.Count);
    }

    [Fact]
    public async Task Open_receipt_keeps_returned_document_identity_when_active_document_changes()
    {
        Directory.CreateDirectory(_directory);
        var application = new FakeApplication("14.2.0", null);
        var unrelated = new FakeDocument("unrelated", "tc://other", FakeNode.FlatTree(1));
        var worker = new OnlineMaterialTeamcenterWorker(Path.Combine(_directory, "receipt.vvi"))
        { AfterConsume = () => application.ActiveDocument = unrelated };
        using var runtime = new TeamcenterReadOnlyRuntime(worker, Path.Combine(_directory, "tc.db"));
        await runtime.LoginAsync("tc-production", "user", "secret", default);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application, ProcessId = 123, ProcessStartUtcTicks = 456 },
            _directory, Path.Combine(_directory, "tree.db"), runtime);
        var result = await adapter.ExecuteAsync(new AdapterOperation("teamcenter.visualization.launch@2", OnlineSelectorPayload()), default);
        Assert.True(result.Ok);
        var receipt = JsonSerializer.SerializeToElement(result.Data);
        var identity = receipt.GetProperty("document_identity");
        Assert.Same(unrelated, application.ActiveDocument);
        Assert.Equal(application.LastOpenedDocument!.DocumentId, identity.GetProperty("document_handle").GetString());
        Assert.Equal(123, identity.GetProperty("process_id").GetInt32());
        Assert.Equal("456", identity.GetProperty("process_started_utc_ticks").GetString());
        Assert.Equal(CanonicalJson.Hash(new { process_id = 123, process_started_utc_ticks = "456",
            document_handle = application.LastOpenedDocument.DocumentId }), identity.GetProperty("document_session").GetString());
        Assert.Equal("ai00.viewer.opened-source.v1", receipt.GetProperty("protocol").GetString());
        Assert.StartsWith("sha256:", receipt.GetProperty("launch").GetProperty("source_identity_hash").GetString());
    }

    [Fact]
    public async Task Open_receipt_requires_process_identity_before_opening_model()
    {
        Directory.CreateDirectory(_directory);
        var application = new FakeApplication("14.2.0", null);
        var worker = new OnlineMaterialTeamcenterWorker(Path.Combine(_directory, "no-process.vvi"));
        using var runtime = new TeamcenterReadOnlyRuntime(worker, Path.Combine(_directory, "tc.db"));
        await runtime.LoginAsync("tc-production", "user", "secret", default);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application }, _directory, Path.Combine(_directory, "tree.db"), runtime);
        await Assert.ThrowsAsync<ConnectorException>(() => adapter.OpenTeamcenterVisualizationWithIdentityAsync(
            OnlineSelectorPayload(), CancellationToken.None));
        Assert.Null(application.LastOpenedDocument);
    }

    [Fact]
    public async Task Teamcenter_online_launch_opens_a_new_document_and_deletes_material()
    {
        Directory.CreateDirectory(_directory);
        var worker = new OnlineMaterialTeamcenterWorker(Path.Combine(_directory, "online.vvi"));
        using var runtime = new TeamcenterReadOnlyRuntime(worker, Path.Combine(_directory, "tc.db"));
        await runtime.LoginAsync("tc-production", "user", "secret", default);
        var existing = new FakeDocument("existing", "user", FakeNode.FlatTree(1));
        var opened = new FakeDocument("online", OnlineNativeSource, FakeNode.FlatTree(1));
        var application = new FakeApplication("14.2.0", existing);
        var launcher = new RecordingTeamcenterVisualizationLauncher(() =>
        {
            application.ActiveDocument = opened;
            application.OpenDocuments = [existing, opened];
        });
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application }, _directory,
            Path.Combine(_directory, "tree.db"), runtime, launcher);

        var result = await adapter.ExecuteAsync(new AdapterOperation(
            "teamcenter.visualization.launch@1", OnlineSelectorPayload()), default);

        Assert.True(result.Ok);
        Assert.Null(launcher.MaterialPath);
        Assert.Equal("Open", worker.VisualizationOperation);
        Assert.NotNull(application.LastOpenedDocument);
        Assert.Same(application.LastOpenedDocument, application.ActiveDocument);
        Assert.Equal(Path.GetFullPath(worker.MaterialPath), application.LastOpenedDocument.SourceIdentity);
        Assert.False(File.Exists(worker.MaterialPath));
    }

    [Fact]
    public async Task Teamcenter_online_launch_creates_owned_session_and_opens_material_there()
    {
        Directory.CreateDirectory(_directory);
        var worker = new OnlineMaterialTeamcenterWorker(Path.Combine(_directory, "owned.vvi"));
        using var runtime = new TeamcenterReadOnlyRuntime(worker, Path.Combine(_directory, "tc.db"));
        await runtime.LoginAsync("tc-production", "user", "secret", default);
        var application = new FakeApplication("14.2.0", null);
        var com = new FakeVisMockupCom { LaunchedApplication = application };
        var launcher = new RecordingTeamcenterVisualizationLauncher(() =>
        {
            Assert.Same(application, com.ExistingApplication);
            Assert.True(com.HideOwnedWindowsCalls > 0);
            application.ActiveDocument = new FakeDocument("online", OnlineNativeSource, FakeNode.FlatTree(1));
            application.OpenDocuments = [application.ActiveDocument];
        });
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]), com, _directory,
            Path.Combine(_directory, "tree.db"), runtime, launcher);

        var result = await adapter.ExecuteAsync(new AdapterOperation(
            "teamcenter.visualization.launch@1", OnlineSelectorPayload()), default);

        Assert.True(result.Ok);
        Assert.Equal(1, com.LaunchCalls);
        Assert.True(com.HideOwnedWindowsCalls >= 2);
        Assert.Null(launcher.MaterialPath);
        Assert.NotNull(application.LastOpenedDocument);
        Assert.Same(application.LastOpenedDocument, application.ActiveDocument);
        Assert.False(File.Exists(worker.MaterialPath));
    }

    [Fact]
    public void Teamcenter_online_launcher_uses_the_official_runner_contract_and_utf16be_path()
    {
        Directory.CreateDirectory(_directory);
        var runnerPath = Path.Combine(_directory, "runner.exe");
        var materialPath = Path.Combine(_directory, "online.vvi");
        File.WriteAllBytes(runnerPath, [1]);
        File.WriteAllText(materialPath, "[VVI]");
        var launcher = new TeamcenterVisualizationRunner(runnerPath);

        var start = launcher.CreateStartInfo(materialPath);

        Assert.Equal(Path.GetFullPath(runnerPath), start.FileName);
        Assert.Equal("-mime=application/x-visnetwork", start.ArgumentList[0]);
        Assert.Equal("-encodedArgs=" + Convert.ToHexString(System.Text.Encoding.BigEndianUnicode.GetBytes(Path.GetFullPath(materialPath))), start.ArgumentList[1]);
        Assert.False(start.UseShellExecute);
    }

    [Theory]
    [InlineData(".vvi")]
    [InlineData(".jt")]
    public async Task Teamcenter_online_insert_uses_the_current_document_and_deletes_material(string extension)
    {
        Directory.CreateDirectory(_directory);
        var worker = new OnlineMaterialTeamcenterWorker(Path.Combine(_directory, "insert" + extension));
        using var runtime = new TeamcenterReadOnlyRuntime(worker, Path.Combine(_directory, "tc.db"));
        await runtime.LoginAsync("tc-production", "user", "secret", default);
        var active = new FakeDocument("active", "user", FakeNode.FlatTree(1));
        var application = new FakeApplication("14.2.0", active);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application }, _directory, Path.Combine(_directory, "tree.db"), runtime);

        var result = await adapter.ExecuteAsync(new AdapterOperation(
            "teamcenter.visualization.insert@1", OnlineSelectorPayload()), default);

        Assert.True(result.Ok);
        Assert.Equal("Insert", worker.VisualizationOperation);
        Assert.Same(active, application.ActiveDocument);
        Assert.Equal(1, active.InsertDocumentCalls);
        Assert.False(File.Exists(worker.MaterialPath));
        Assert.Contains(adapter.Manifest.Operations, item => item.OperationId == "teamcenter.visualization.insert@1");
    }

    [Fact]
    public async Task Teamcenter_online_insert_fails_closed_without_an_active_document_and_cleans_material()
    {
        Directory.CreateDirectory(_directory);
        var worker = new OnlineMaterialTeamcenterWorker(Path.Combine(_directory, "orphan.vvi"));
        using var runtime = new TeamcenterReadOnlyRuntime(worker, Path.Combine(_directory, "tc.db"));
        await runtime.LoginAsync("tc-production", "user", "secret", default);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", null) },
            _directory, Path.Combine(_directory, "tree.db"), runtime);

        var error = await Assert.ThrowsAsync<ConnectorException>(() => adapter.ExecuteAsync(new AdapterOperation(
            "teamcenter.visualization.insert@1", OnlineSelectorPayload()), default));

        Assert.Equal("vismockup_active_document_required", error.Message);
        Assert.False(File.Exists(worker.MaterialPath));
    }

    private static JsonElement OnlineSelectorPayload() => JsonSerializer.SerializeToElement(new
    {
        source_selector = new { endpoint_id = "tc-production", object_uid = "item", item_revision_uid = "revision",
            bom_view_uid = "", revision_rule = "Latest Working", configuration_date = "2026-09-16T00:00:00Z" },
        expected_visdoc_uid = "",
    });

    private const string OnlineNativeSource = "http://tc.example/tc?VVI_Version=3.0?VisDoc_UID=bom-123?VisDoc_Type=BOMView%20Revision?Operation=Open";

    [Theory]
    [InlineData(".vvi")]
    [InlineData(".jt")]
    public async Task Teamcenter_open_uses_the_current_renderer_without_a_historical_source_receipt(string extension)
    {
        Directory.CreateDirectory(_directory);
        var worker = new OnlineMaterialTeamcenterWorker(Path.Combine(_directory, "fresh" + extension));
        using var runtime = new TeamcenterReadOnlyRuntime(worker, Path.Combine(_directory, "tc.db"));
        await runtime.LoginAsync("tc-production", "user", "secret", default);
        var existing = new FakeDocument("existing", OnlineNativeSource, FakeNode.FlatTree(1));
        var application = new FakeApplication("14.2.0", existing);
        var launcher = new RecordingTeamcenterVisualizationLauncher();
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application }, _directory,
            Path.Combine(_directory, "tree.db"), runtime, launcher);

        var result = await adapter.ExecuteAsync(new AdapterOperation(
            "teamcenter.visualization.launch@1", OnlineSelectorPayload()), default);

        Assert.True(result.Ok);
        Assert.Null(launcher.MaterialPath);
        Assert.NotNull(application.LastOpenedDocument);
        Assert.NotSame(existing, application.LastOpenedDocument);
        Assert.Same(application.LastOpenedDocument, application.ActiveDocument);
        Assert.Equal(Path.GetFullPath(worker.MaterialPath), application.LastOpenedDocument!.SourceIdentity);
        Assert.Equal([existing, application.LastOpenedDocument], application.OpenDocuments);
        Assert.False(File.Exists(worker.MaterialPath));
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    public async Task Direct_JT_material_opens_in_renderer_without_discovering_matching_documents(bool reuse, bool ambiguous)
    {
        const string source="http://tc.example/tc?Title=bolt/01;1?original_file_name=bolt_01.jt?ref_name=JTPART?FileTypeID=DirectModel.Document?Operation=Open";
        Directory.CreateDirectory(_directory);
        var worker=new OnlineMaterialTeamcenterWorker(Path.Combine(_directory,"leaf.vvi")) {
            MaterialOverride="HostPath=http://tc.example/tc\nOperation=Open\nTitle=bolt/01;1\noriginal_file_name=bolt_01.jt\nref_name=JTPART\nFileTypeID=DirectModel.Document\n"
        };
        using var runtime=new TeamcenterReadOnlyRuntime(worker,Path.Combine(_directory,"tc.db"));
        await runtime.LoginAsync("tc-production","user","secret",default);
        var existing=new FakeDocument("old",reuse?source:"user",FakeNode.FlatTree(1));
        var opened=new FakeDocument("new",source,FakeNode.FlatTree(1));
        var application=new FakeApplication("14.2.0",existing) { OpenDocuments=[existing] };
        var launcher=new RecordingTeamcenterVisualizationLauncher(()=> {
            if (reuse) return;
            application.ActiveDocument=opened;
            application.OpenDocuments=ambiguous
                ? [existing,opened,new FakeDocument("other-new",source,FakeNode.FlatTree(1))]
                : [existing,opened];
        });
        using var sta=new StaDispatcher();
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication=application },_directory,Path.Combine(_directory,"tree.db"),runtime,launcher);
        using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(1));
        var operation=new AdapterOperation("teamcenter.visualization.launch@1",OnlineSelectorPayload());
        Assert.True((await adapter.ExecuteAsync(operation,timeout.Token)).Ok);
        Assert.Null(launcher.MaterialPath);
        Assert.NotNull(application.LastOpenedDocument);
        Assert.Same(application.LastOpenedDocument,application.ActiveDocument);
        Assert.False(File.Exists(worker.MaterialPath));
    }

    [Theory]
    [InlineData("same")] [InlineData("pid")] [InlineData("started")] [InlineData("dataset")]
    [InlineData("file")] [InlineData("document")] [InlineData("live_source")] [InlineData("ambiguous")]
    public async Task Explicit_open_uses_current_TC_material_after_runtime_or_source_changes(string change)
    {
        Directory.CreateDirectory(_directory);
        const string live="http://tc.example/tc?Title=bolt/01;1?original_file_name=bolt_01.jt?ref_name=JTPART?FileTypeID=DirectModel.Document?Operation=Open";
        var worker=new OnlineMaterialTeamcenterWorker(Path.Combine(_directory,"receipt.vvi")) {
            MaterialOverride="HostPath=http://tc.example/tc\nOperation=Open\nVisDoc_UID=dataset-1\nVisDoc_Type=DirectModel\n",
            SourceEvidence="{\"dataset_uid\":\"dataset-1\",\"file_uid\":\"file-1\",\"file_name\":\"bolt_01.jt\"}"
        };
        using var runtime=new TeamcenterReadOnlyRuntime(worker,Path.Combine(_directory,"tc.db"));
        await runtime.LoginAsync("tc-production","user","secret",default);
        var document=new FakeDocument("opened",live,FakeNode.FlatTree(1));
        var application=new FakeApplication("14.2.0",null) {OpenDocuments=[]};
        var com=new FakeVisMockupCom {ExistingApplication=application,ProcessId=100,ProcessStartUtcTicks=200};
        var firstLauncher=new RecordingTeamcenterVisualizationLauncher(()=>{application.ActiveDocument=document;application.OpenDocuments=[document];});
        using var sta=new StaDispatcher();
        var path=Path.Combine(_directory,"tree.db");
        var operation=new AdapterOperation("teamcenter.visualization.launch@1",OnlineSelectorPayload());
        Assert.True((await new VisMockupAdapter(sta,new AllowedPathPolicy([_directory]),com,_directory,path,runtime,firstLauncher)
            .ExecuteAsync(operation,default)).Ok);
        var firstOpened = application.LastOpenedDocument;
        Assert.NotNull(firstOpened);
        Assert.Null(firstLauncher.MaterialPath);
        if(change=="pid")com.ProcessId++;
        if(change=="started")com.ProcessStartUtcTicks++;
        if(change=="dataset") {worker.MaterialOverride=worker.MaterialOverride.Replace("dataset-1","dataset-2");worker.SourceEvidence=worker.SourceEvidence.Replace("dataset-1","dataset-2");}
        if(change=="file")worker.SourceEvidence=worker.SourceEvidence.Replace("file-1","file-2");
        if(change=="ambiguous")application.OpenDocuments=[document,new FakeDocument("duplicate",live,FakeNode.FlatTree(1))];
        if(change is "document" or "live_source") {
            document=new FakeDocument(change=="document"?"replaced":"opened",change=="live_source"?live.Replace("bolt/01;1","other/01;1"):live,FakeNode.FlatTree(1));
            application.ActiveDocument=document;application.OpenDocuments=[document];
        }
        var secondLauncher=new RecordingTeamcenterVisualizationLauncher();
        var restarted=new VisMockupAdapter(sta,new AllowedPathPolicy([_directory]),com,_directory,path,runtime,secondLauncher);
        using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(1));
        Assert.True((await restarted.ExecuteAsync(operation,timeout.Token)).Ok);
        Assert.NotSame(firstOpened,application.LastOpenedDocument);
        Assert.Same(application.LastOpenedDocument,application.ActiveDocument);
        Assert.Null(secondLauncher.MaterialPath);
    }

    [Fact]
    public async Task Online_open_calls_renderer_even_when_existing_document_has_the_same_TC_source()
    {
        Directory.CreateDirectory(_directory);
        var worker=new OnlineMaterialTeamcenterWorker(Path.Combine(_directory,"same.vvi"));
        using var runtime=new TeamcenterReadOnlyRuntime(worker,Path.Combine(_directory,"tc.db"));
        await runtime.LoginAsync("tc-production","user","secret",default);
        var document=new FakeDocument("unchanged",OnlineNativeSource,FakeNode.FlatTree(1));
        var application=new FakeApplication("14.2.0",document);
        using var sta=new StaDispatcher();
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom {ExistingApplication=application},_directory,Path.Combine(_directory,"tree.db"),
            runtime,new RecordingTeamcenterVisualizationLauncher());
        using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(1));
        var result=await adapter.ExecuteAsync(new AdapterOperation("teamcenter.visualization.launch@1",OnlineSelectorPayload()),timeout.Token);
        Assert.True(result.Ok);
        Assert.NotNull(application.LastOpenedDocument);
        Assert.NotSame(document,application.ActiveDocument);
        Assert.False(File.Exists(worker.MaterialPath));
    }

    [Theory]
    [InlineData("http://tc.example/tc?VisDoc_UID=other?VisDoc_Type=BOMView%20Revision")]
    [InlineData("http://other.example/tc?VisDoc_UID=bom-123?VisDoc_Type=BOMView%20Revision")]
    public async Task Online_open_uses_returned_document_instead_of_adopting_an_unrelated_active_document(string source)
    {
        Directory.CreateDirectory(_directory);
        var worker=new OnlineMaterialTeamcenterWorker(Path.Combine(_directory,"wrong.vvi"));
        using var runtime=new TeamcenterReadOnlyRuntime(worker,Path.Combine(_directory,"tc.db"));
        await runtime.LoginAsync("tc-production","user","secret",default);
        var unrelated=new FakeDocument("unrelated",source,FakeNode.FlatTree(1));
        var application=new FakeApplication("14.2.0",unrelated);
        var launcher=new RecordingTeamcenterVisualizationLauncher(()=>application.ActiveDocument=new FakeDocument("changed",source,FakeNode.FlatTree(1)));
        using var sta=new StaDispatcher();
        var adapter=new VisMockupAdapter(sta,new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom {ExistingApplication=application},_directory,Path.Combine(_directory,"tree.db"),runtime,launcher);
        using var timeout=new CancellationTokenSource(TimeSpan.FromMilliseconds(200));
        Assert.True((await adapter.ExecuteAsync(
            new AdapterOperation("teamcenter.visualization.launch@1",OnlineSelectorPayload()),timeout.Token)).Ok);
        Assert.Null(launcher.MaterialPath);
        Assert.NotNull(application.LastOpenedDocument);
        Assert.Same(application.LastOpenedDocument,application.ActiveDocument);
        Assert.NotSame(unrelated,application.ActiveDocument);
        Assert.False(File.Exists(worker.MaterialPath));
    }

    [Fact]
    public async Task OpensAndClosesAllDocumentsInTheConnectedApplication()
    {
        Directory.CreateDirectory(_directory);
        var path = Path.Combine(_directory, "model.jt");
        File.WriteAllBytes(path, [1, 2, 3]);
        var application = new FakeApplication("14.2.0", null);
        var fake = new FakeVisMockupCom { ExistingApplication = application };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]), fake);

        var opened = await adapter.ExecuteAsync(new AdapterOperation(
            "vismockup.model.open@1", JsonSerializer.SerializeToElement(new { local_artifact_path = path })), default);
        var closed = await adapter.ExecuteAsync(new AdapterOperation(
            "vismockup.model.close@1", JsonSerializer.SerializeToElement(new { })), default);

        Assert.True(opened.Ok);
        Assert.True(closed.Ok);
        Assert.True(application.LastOpenedDocument!.Closed);
    }

    [Fact]
    public async Task InsertsIntoTheActiveDocumentWithoutOpeningAnotherDocumentAndSkipsDuplicatePath()
    {
        Directory.CreateDirectory(_directory);
        var insertedPath = Path.Combine(_directory, "inserted.jt");
        File.WriteAllBytes(insertedPath, [1, 2, 3]);
        var active = new FakeDocument("active-document", "primary.plmxml", FakeNode.FlatTree(1));
        var application = new FakeApplication("14.2.0", active);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application });

        var first = await adapter.ExecuteAsync(new AdapterOperation(
            "vismockup.model.insert@1",
            JsonSerializer.SerializeToElement(new { local_artifact_path = insertedPath }),
            "insert-step-1"), default);
        var second = await adapter.ExecuteAsync(new AdapterOperation(
            "vismockup.model.insert@1",
            JsonSerializer.SerializeToElement(new { local_artifact_path = insertedPath }),
            "insert-step-1"), default);

        Assert.True(first.Ok);
        Assert.True(second.Ok);
        Assert.Same(active, application.ActiveDocument);
        Assert.Equal(1, active.InsertDocumentCalls);
        Assert.Equal([Path.GetFullPath(insertedPath)], active.InsertedDocumentPaths);
        Assert.Contains(adapter.Manifest.Operations,
            item => item.OperationId == "vismockup.model.insert@1");
    }

    [Fact]
    public void WindowsComDocumentInsertUsesTheDocumentDispatchContract()
    {
        var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
        var source = File.ReadAllText(Path.Combine(root, "src", "Ai00.Connector.Adapters.VisMockup", "IVisMockupCom.cs"));

        Assert.Contains("VisMockupDispatch.InvokeMethod(value, 1, path)", source);
        Assert.Contains("VisMockupDispatch.GetProperty(value, 8)", source);
        Assert.Contains("VisMockupDispatch.GetProperty(value, 12, index)", source);
        var insertStart = source.LastIndexOf("public string InsertDocument", StringComparison.Ordinal);
        var insertEnd = source.IndexOf("public void CaptureImage", insertStart, StringComparison.Ordinal);
        Assert.DoesNotContain("AddModel(path)", source[insertStart..insertEnd]);
    }


    [Fact]
    public async Task CloseTakesOverVisMockupAndClosesUserSelectedDocumentsToo()
    {
        Directory.CreateDirectory(_directory);
        var path = Path.Combine(_directory, "model.jt");
        File.WriteAllBytes(path, [1]);
        var application = new FakeApplication("14.2.0", null);
        var fake = new FakeVisMockupCom { ExistingApplication = application };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]), fake);
        await adapter.ExecuteAsync(new AdapterOperation(
            "vismockup.model.open@1", JsonSerializer.SerializeToElement(new { local_artifact_path = path })), default);
        var ownedDocument = application.LastOpenedDocument!;
        var userDocument = new FakeDocument("user-document", "user", FakeNode.FlatTree(1));
        application.ActiveDocument = userDocument;

        var result = await adapter.ExecuteAsync(new AdapterOperation(
            "vismockup.model.close@1", JsonSerializer.SerializeToElement(new { })), default);

        Assert.True(result.Ok);
        Assert.True(ownedDocument.Closed);
        Assert.True(userDocument.Closed);
    }

    [Fact]
    public async Task CloseWorksWhenAi00DidNotOpenTheDocument()
    {
        var existingDocument = new FakeDocument("existing-document", "user", FakeNode.FlatTree(1));
        var application = new FakeApplication("14.2.0", existingDocument);
        var fake = new FakeVisMockupCom { ExistingApplication = application };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]), fake);

        var result = await adapter.ExecuteAsync(new AdapterOperation(
            "vismockup.model.close@1", JsonSerializer.SerializeToElement(new { })), default);

        Assert.True(result.Ok);
        Assert.True(existingDocument.Closed);
    }

    [Fact]
    public void WindowsComAdapterUsesTheVisMockupCloseAllDocumentsContract()
    {
        var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
        var source = File.ReadAllText(Path.Combine(root, "src", "Ai00.Connector.Adapters.VisMockup", "IVisMockupCom.cs"));

        Assert.Contains("var documents = VisMockupDispatch.GetProperty(value, 4);", source);
        Assert.Contains("VisMockupDispatch.InvokeMethod(documents, 4)", source);
        Assert.DoesNotContain("vismockup-close-method-error", source);
    }

    [Fact]
    public void WindowsComAdapterUsesOwnedOuterDocumentCollectionContract()
    {
        var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
        var source = File.ReadAllText(Path.Combine(root, "src", "Ai00.Connector.Adapters.VisMockup", "IVisMockupCom.cs"));

        Assert.Contains("VisMockupDispatch.InvokeMethod(documents, 5, path)", source);
        Assert.Contains("VisMockupDispatch.SetProperty(outer, 1, true)", source);
        Assert.Contains("HideOwnedWindows();", source);
        Assert.DoesNotContain("VisMockupDispatch.SetProperty(value, 1, true)", source);
        Assert.Contains("ReadActiveDocument", source);
        Assert.Contains("error.Code.StartsWith(\"vismockup_dispatch_d4_\"", source);
        Assert.DoesNotContain("Value.Documents.Open(path)", source);
    }

    [Fact]
    public void WindowsComAdapterResolvesNodeKeysWithoutWalkingTheWholeTree()
    {
        var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
        var source = File.ReadAllText(Path.Combine(root, "src", "Ai00.Connector.Adapters.VisMockup", "IVisMockupCom.cs"));

        Assert.Contains("view.GetNodeFromKey(numericKey, ref found)", source);
        Assert.Contains("VisMockupDispatch.SetProperty(node, 10, selected)", source);
    }

    [Fact]
    public async Task GovernedVisibilityOperationChangesAllNodes()
    {
        var document = new FakeDocument("existing-document", "user", FakeNode.FlatTree(3));
        var application = new FakeApplication("14.2.0", document);
        var fake = new FakeVisMockupCom { ExistingApplication = application };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]), fake);

        var hidden = await adapter.ExecuteAsync(new AdapterOperation(
            "vismockup.visibility.change@1", JsonSerializer.SerializeToElement(new { action = "all_off" })), default);
        var shown = await adapter.ExecuteAsync(new AdapterOperation(
            "vismockup.visibility.change@1", JsonSerializer.SerializeToElement(new { action = "all_on" })), default);

        Assert.True(hidden.Ok);
        Assert.True(shown.Ok);
        Assert.Equal([false, true], document.VisibilityChanges);
    }

    [Fact]
    public async Task GovernedNodeOperationsUseTheTreeNodeKey()
    {
        var document = new FakeDocument("existing-document", "user", FakeNode.FlatTree(3));
        var application = new FakeApplication("14.2.0", document);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application });

        var visible = await adapter.ExecuteAsync(new AdapterOperation(
            "vismockup.node.visibility.change@1",
            JsonSerializer.SerializeToElement(new { node_key = "node-1", action = "show" })), default);
        var selected = await adapter.ExecuteAsync(new AdapterOperation(
            "vismockup.node.selection.change@1",
            JsonSerializer.SerializeToElement(new { node_key = "node-1", action = "highlight" })), default);

        Assert.True(visible.Ok);
        Assert.True(selected.Ok);
        Assert.Contains("node-1", document.VisibleNodeKeys);
        Assert.Contains("node-1", document.SelectedNodeKeys);
        Assert.Contains(adapter.Manifest.Operations, item => item.OperationId == "vismockup.node.visibility.change@1");
        Assert.Contains(adapter.Manifest.Operations, item => item.OperationId == "vismockup.node.selection.change@1");
    }

    [Fact]
    public async Task GovernedNodeVisibilityRejectsAStaleExpectedDocumentBeforeWriting()
    {
        var document = new FakeDocument("existing-document", "user", FakeNode.FlatTree(3));
        var application = new FakeApplication("14.2.0", document);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application, ProcessId = 100, ProcessStartUtcTicks = 200 });

        var error = await Assert.ThrowsAsync<ConnectorException>(() => adapter.ExecuteAsync(new AdapterOperation(
            "vismockup.node.visibility.change@1",
            JsonSerializer.SerializeToElement(new {
                node_key = "node-1", action = "hide",
                expected_document_session = "sha256:" + new string('a', 64),
            })), default));

        Assert.Equal("vismockup_document_changed", error.Message);
        Assert.Empty(document.VisibleNodeKeys);
    }

    [Fact]
    public async Task OnlineOccurrenceKeyResolvesToTheUniqueLiveVisMockupInstance()
    {
        var document = new FakeDocument("existing-document", "tc://bom/1",
            new FakeNode("session-root", "Root", "root-occ", "root", [
                new FakeNode("session-leaf", "Leaf", "tc-occ-42", "part", []),
            ]));
        var application = new FakeApplication("14.2.0", document);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application });

        await adapter.ChangeNodeVisibilityAsync("tc:tc-occ-42", "show");
        await adapter.ChangeNodeSelectionAsync("tc:tc-occ-42", "highlight");

        Assert.Contains("session-leaf", document.VisibleNodeKeys);
        Assert.Contains("session-leaf", document.SelectedNodeKeys);
    }

    [Fact]
    public async Task OnlineOccurrenceKeyFailsClosedWhenLiveIdentityIsAmbiguous()
    {
        var document = new FakeDocument("existing-document", "tc://bom/1",
            new FakeNode("session-root", "Root", "root-occ", "root", [
                new FakeNode("session-left", "Same Part", "duplicate-occ", "part", []),
                new FakeNode("session-right", "Same Part", "duplicate-occ", "part", []),
            ]));
        var application = new FakeApplication("14.2.0", document);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application });

        var error = await Assert.ThrowsAsync<ConnectorNoEffectException>(
            () => adapter.ChangeNodeVisibilityAsync("tc:duplicate-occ", "hide"));

        Assert.Equal("vismockup_online_occurrence_ambiguous", error.Message);
        Assert.Empty(document.VisibleNodeKeys);
    }

    [Fact]
    public async Task OnlineOccurrencePathHashFailsClosedBeforeVisMockupLookup()
    {
        var document = new FakeDocument("existing-document", "tc://bom/1",
            new FakeNode("session-root", "Root", "root-occ", "root", [
                new FakeNode("session-leaf", "Leaf", "sha256:cached-path", "part", []),
            ]));
        var application = new FakeApplication("14.2.0", document);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application });

        var error = await Assert.ThrowsAsync<ConnectorNoEffectException>(
            () => adapter.ChangeNodeVisibilityAsync("tc:sha256:cached-path", "hide"));

        Assert.Equal("vismockup_online_occurrence_locator_invalid", error.Message);
        Assert.Equal(0, document.SetNodeVisibleCalls);
    }

    [Fact]
    public async Task NodeVisibilityDoesNotSkipDisplayForAnAlreadyVisibleUnloadedNode()
    {
        var document = new FakeDocument("existing-document", "user", FakeNode.FlatTree(1));
        document.SetNodeVisible("node-0", true);
        var application = new FakeApplication("14.2.0", document);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application });
        var callsBefore = document.SetNodeVisibleCalls;

        var result = await adapter.ChangeNodeVisibilityAsync("node-0", "show");

        Assert.Equal(callsBefore + 1, document.SetNodeVisibleCalls);
        Assert.Contains("visible = True", result.ToString());
    }

    [Fact]
    public async Task NodeVisibilityAcceptsAWriteThatThrowsAfterTakingEffect()
    {
        var document = new FakeDocument("existing-document", "user", FakeNode.FlatTree(1))
        {
            SetNodeVisibleError = new InvalidOperationException("late COM failure"),
            ApplyVisibilityBeforeThrow = true,
        };
        var application = new FakeApplication("14.2.0", document);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application });

        var result = await adapter.ChangeNodeVisibilityAsync("node-0", "show");

        Assert.True(document.IsNodeVisible("node-0"));
        Assert.Contains("visible = True", result.ToString());
    }

    [Fact]
    public async Task NodeVisibilityClassifiesARejectedWriteAsNoEffect()
    {
        var document = new FakeDocument("existing-document", "user", FakeNode.FlatTree(1))
        {
            SetNodeVisibleError = new InvalidOperationException("COM rejected write"),
        };
        var application = new FakeApplication("14.2.0", document);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application });

        var error = await Assert.ThrowsAsync<ConnectorNoEffectException>(
            () => adapter.ChangeNodeVisibilityAsync("node-0", "show"));

        Assert.Equal("vismockup_node_visibility_write_rejected", error.Message);
        Assert.False(document.IsNodeVisible("node-0"));
    }

    [Fact]
    public async Task ReadOnlyVisibilityRecoveryFindsTheTargetInANonActiveOpenDocument()
    {
        Directory.CreateDirectory(_directory);
        var active = new FakeDocument("active", "tc://active", FakeNode.FlatTree(1));
        var target = new FakeDocument("target", "tc://target",
            new FakeNode("session-root", "Root", "", "", [
                new FakeNode("session-leaf", "Leaf", "", "", []),
            ]));
        var cachePath = Path.Combine(_directory, "tree.db");
        new VisMockupTreeCache(cachePath).ReplaceProjection(target, new("pdm:root", [
            new("pdm:root", null, 0, 0, "Root", "W10", "A", "root", "", [], ["Root"], ""),
            new("pdm:leaf", "pdm:root", 0, 1, "Leaf", "W10-1", "A", "leaf", "", [], ["Root", "Leaf"], ""),
        ], "sha256:" + new string('d', 64)));
        var application = new FakeApplication("14.2.0", active) { OpenDocuments = [active, target] };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application }, Path.Combine(_directory, "captures"), cachePath);

        var visible = await adapter.ObserveNodeVisibilityAsync("pdm:leaf");

        Assert.False(visible);
    }

    [Fact]
    public async Task ReadOnlyVisibilityRecoveryRejectsACachedTargetWhoseDocumentIsClosed()
    {
        Directory.CreateDirectory(_directory);
        var active = new FakeDocument("active", "tc://active", FakeNode.FlatTree(1));
        var closed = new FakeDocument("closed", "tc://closed",
            new FakeNode("session-root", "Root", "", "", [
                new FakeNode("session-leaf", "Leaf", "", "", []),
            ]));
        var cachePath = Path.Combine(_directory, "tree.db");
        new VisMockupTreeCache(cachePath).ReplaceProjection(closed, new("pdm:root", [
            new("pdm:root", null, 0, 0, "Root", "W10", "A", "root", "", [], ["Root"], ""),
            new("pdm:leaf", "pdm:root", 0, 1, "Leaf", "W10-1", "A", "leaf", "", [], ["Root", "Leaf"], ""),
        ], "sha256:" + new string('e', 64)));
        var application = new FakeApplication("14.2.0", active) { OpenDocuments = [active] };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application }, Path.Combine(_directory, "captures"), cachePath);

        var error = await Assert.ThrowsAsync<ConnectorException>(
            () => adapter.ObserveNodeVisibilityAsync("pdm:leaf"));

        Assert.Equal("vismockup_recovery_node_unavailable", error.Code);
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory)) Directory.Delete(_directory, true);
    }

    private sealed class OnlineMaterialTeamcenterWorker(string materialPath) : ITeamcenterWorker
    {
        public string MaterialPath { get; } = materialPath;
        public string? MaterialOverride { get; set; }
        public string? SourceEvidence { get; set; }
        public string? VisualizationOperation { get; private set; }
        public Action? AfterConsume { get; init; }
        public Task ValidateCredentialsAsync(string endpointId, string username, string password, CancellationToken ct) => Task.CompletedTask;
        public Task<IReadOnlyList<string>> GetRevisionRulesAsync(string username, string password, CancellationToken ct) => Task.FromResult<IReadOnlyList<string>>(["Latest Working"]);
        public Task<TeamcenterProductSearchResult> SearchAsync(string itemId, string revisionId, string revisionRule, string configurationDate, string username, string password, CancellationToken ct) => Task.FromResult(new TeamcenterProductSearchResult([]));
        public Task<IReadOnlyList<TeamcenterOccurrence>> ObserveAsync(TeamcenterSourceSelector selector, int maxNodes, int maxDepth, string propertyProjection, string username, string password, CancellationToken ct) => Task.FromResult<IReadOnlyList<TeamcenterOccurrence>>([]);
        public Task<TeamcenterLaunchResult> LaunchAsync(TeamcenterSourceSelector selector, string expectedVisdocUid, string username, string password, CancellationToken ct) => throw new NotSupportedException();
        public async Task<TeamcenterLaunchResult> ConsumeVisualizationAsync(TeamcenterSourceSelector selector,
            string expectedVisdocUid, string visualizationOperation, Func<string, CancellationToken, Task> consumer,
            string username, string password, CancellationToken ct)
        {
            VisualizationOperation = visualizationOperation;
            await File.WriteAllTextAsync(MaterialPath, MaterialOverride ?? "VVI_Version=3.0\nHostPath=http://tc.example/tc\nVisDoc_UID=bom-123\nVisDoc_Type=BOMView%20Revision\nOperation="+visualizationOperation, ct);
            if(SourceEvidence is not null)await File.WriteAllTextAsync(MaterialPath+".source.json",SourceEvidence,ct);
            try { await consumer(MaterialPath, ct); AfterConsume?.Invoke(); }
            finally { File.Delete(MaterialPath); File.Delete(MaterialPath+".source.json"); }
            return new("tclaunch:" + new string('a', 64), true, expectedVisdocUid, selector.IdentityHash);
        }
    }

    private sealed class RecordingTeamcenterVisualizationLauncher(Action? onLaunch = null) : ITeamcenterVisualizationLauncher
    {
        public string? MaterialPath { get; private set; }
        public Task LaunchAsync(string materialPath, CancellationToken ct)
        {
            MaterialPath = Path.GetFullPath(materialPath);
            onLaunch?.Invoke();
            return Task.CompletedTask;
        }
    }
}
