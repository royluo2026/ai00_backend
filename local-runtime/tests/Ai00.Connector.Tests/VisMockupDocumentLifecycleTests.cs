using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupDocumentLifecycleTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), "ai00-vismockup-lifecycle", Guid.NewGuid().ToString("N"));

    [Fact]
    public async Task Teamcenter_online_launch_opens_a_new_document_and_deletes_material()
    {
        Directory.CreateDirectory(_directory);
        var worker = new OnlineMaterialTeamcenterWorker(Path.Combine(_directory, "online.vvi"));
        using var runtime = new TeamcenterReadOnlyRuntime(worker, Path.Combine(_directory, "tc.db"));
        await runtime.LoginAsync("tc-production", "user", "secret", default);
        var application = new FakeApplication("14.2.0", new FakeDocument("existing", "user", FakeNode.FlatTree(1)));
        var launcher = new RecordingTeamcenterVisualizationLauncher();
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([_directory]),
            new FakeVisMockupCom { ExistingApplication = application }, _directory,
            Path.Combine(_directory, "tree.db"), runtime, launcher);

        var result = await adapter.ExecuteAsync(new AdapterOperation(
            "teamcenter.visualization.launch@1", OnlineSelectorPayload()), default);

        Assert.True(result.Ok);
        Assert.Equal(Path.GetFullPath(worker.MaterialPath), launcher.MaterialPath);
        Assert.Equal("Open", worker.VisualizationOperation);
        Assert.Null(application.LastOpenedDocument);
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

    [Fact]
    public async Task Teamcenter_online_insert_uses_the_current_document_and_deletes_material()
    {
        Directory.CreateDirectory(_directory);
        var worker = new OnlineMaterialTeamcenterWorker(Path.Combine(_directory, "insert.vvi"));
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
        Assert.Contains("VisMockupDispatch.InvokeMethod(documents, 2)", source);
        Assert.DoesNotContain("vismockup-close-method-error", source);
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
        public string? VisualizationOperation { get; private set; }
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
            await File.WriteAllTextAsync(MaterialPath, "[VVI]", ct);
            try { await consumer(MaterialPath, ct); }
            finally { File.Delete(MaterialPath); }
            return new("tclaunch:" + new string('a', 64), true, expectedVisdocUid, selector.IdentityHash);
        }
    }

    private sealed class RecordingTeamcenterVisualizationLauncher : ITeamcenterVisualizationLauncher
    {
        public string? MaterialPath { get; private set; }
        public Task LaunchAsync(string materialPath, CancellationToken ct)
        {
            MaterialPath = Path.GetFullPath(materialPath);
            return Task.CompletedTask;
        }
    }
}
