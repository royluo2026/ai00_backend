using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupDocumentLifecycleTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), "ai00-vismockup-lifecycle", Guid.NewGuid().ToString("N"));

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
        Assert.Contains("VisMockupDispatch.SetProperty(node, 9, visible)", source);
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

    public void Dispose()
    {
        if (Directory.Exists(_directory)) Directory.Delete(_directory, true);
    }
}
