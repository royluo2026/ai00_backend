using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class VisMockupDocumentLimitTests
{
    [Theory]
    [InlineData("VisView")]
    [InlineData("VisView_NG")]
    [InlineData("VisView_ng")]
    public void Capacity_scope_checks_both_native_process_names(string configured)
        => Assert.Equal(new[] { "VisView", "VisView_NG" }, WindowsVisMockupCom.DocumentProcessNames(configured));

    [Theory]
    [InlineData(9, true)]
    [InlineData(10, false)]
    [InlineData(11, false)]
    public void New_document_requires_a_free_slot(int count, bool allowed)
    {
        var app = new CountingApplication(count);
        if (allowed)
        {
            VisMockupDocumentOpen.Open(app, Path.GetFullPath("new.jt"), 123);
            Assert.Equal(10, app.OpenDocumentCount);
        }
        else
            Assert.Equal("vismockup_document_limit_exceeded", Assert.Throws<ConnectorNoEffectException>(() =>
                VisMockupDocumentOpen.Open(app, Path.GetFullPath("new.jt"), 123)).Code);
        Assert.Equal(allowed ? 1 : 0, app.OpenCalls);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void Exact_existing_source_can_be_reused_at_capacity(bool active)
    {
        var app = new CountingApplication(10);
        var path = Path.GetFullPath("existing.jt");
        var existing = new FakeDocument("existing", path, FakeNode.FlatTree(1));
        app.OpenDocuments = [existing];
        if (active) app.ActiveDocument = existing;
        existing.AfterNativeActivation = () => app.ActiveDocument = existing;
        Assert.Same(existing, VisMockupDocumentOpen.Open(app, path, 123));
        Assert.Equal(0, app.OpenCalls);
        Assert.Same(existing, app.ActiveDocument);
    }

    [Fact]
    public void Display_name_is_not_reusable_source_identity()
    {
        var app = new CountingApplication(10) { OpenDocuments = [new FakeDocument("existing", "new.jt", FakeNode.FlatTree(1))] };
        Assert.Equal("vismockup_document_limit_exceeded", Assert.Throws<ConnectorNoEffectException>(() =>
            VisMockupDocumentOpen.Open(app, Path.GetFullPath("new.jt"), 123)).Code);
        Assert.Equal(0, app.OpenCalls);
    }

    [Theory]
    [InlineData("BOMView Revision", true)]
    [InlineData("DirectModel", false)]
    public void Teamcenter_reuse_requires_complete_native_source_identity(string documentType, bool reusable)
    {
        var directory = Path.Combine(Path.GetTempPath(), "ai00-limit", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var path = Path.Combine(directory, "source.vvi");
            File.WriteAllText(path, $"HostPath=http://tc.example/tc\nVisDoc_UID=uid-123\nVisDoc_Type={documentType}\nOperation=Open");
            File.WriteAllText(path + ".source.json", "{\"dataset_uid\":\"uid-123\",\"file_uid\":\"file-123\",\"file_name\":\"part.jt\"}");
            var app = new CountingApplication(10) { ActiveDocument = new FakeDocument("existing",
                $"http://tc.example/tc?VisDoc_UID=uid-123?VisDoc_Type={documentType}", FakeNode.FlatTree(1)) };
            if (reusable) Assert.Same(app.ActiveDocument, VisMockupDocumentOpen.Open(app, path, 123));
            else Assert.Equal("vismockup_document_limit_exceeded", Assert.Throws<ConnectorNoEffectException>(() =>
                VisMockupDocumentOpen.Open(app, path, 123)).Code);
            Assert.Equal(0, app.OpenCalls);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(null)]
    public void Unknown_or_invalid_count_cannot_open(int? count)
    {
        var app = new CountingApplication(count);
        Assert.Equal("vismockup_document_limit_unverifiable", Assert.Throws<ConnectorNoEffectException>(() =>
            VisMockupDocumentOpen.Open(app, Path.GetFullPath("new.jt"), 123)).Code);
        Assert.Equal(0, app.OpenCalls);
    }

    [Fact]
    public async Task Concurrent_adapters_cannot_both_claim_the_last_slot()
    {
        var app = new CountingApplication(9) { OpenDelay = 100 };
        var results = await Task.WhenAll(Enumerable.Range(0, 2).Select(index => Task.Run(() =>
        {
            try { VisMockupDocumentOpen.Open(app, Path.GetFullPath($"new-{index}.jt"), 123); return "opened"; }
            catch (ConnectorNoEffectException error) { return error.Code; }
        })));
        Assert.Single(results, value => value == "opened");
        Assert.Single(results, value => value == "vismockup_document_limit_exceeded");
        Assert.Equal(1, app.OpenCalls);
        Assert.Equal(10, app.OpenDocumentCount);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Managed_and_legacy_file_open_use_the_same_limit(bool legacy)
    {
        var directory = Path.Combine(Path.GetTempPath(), "ai00-limit", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            var path = Path.Combine(directory, "new.jt");
            File.WriteAllText(path, "test");
            var app = new CountingApplication(10);
            using var sta = new StaDispatcher();
            var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([directory]),
                new FakeVisMockupCom { ExistingApplication = app });
            var error = await Assert.ThrowsAsync<ConnectorNoEffectException>(() =>
                legacy ? adapter.OpenFileAsync(path) : adapter.OpenManagedFileAsync(path));
            Assert.Equal("vismockup_document_limit_exceeded", error.Code);
            Assert.Equal(0, app.OpenCalls);
        }
        finally { Directory.Delete(directory, true); }
    }

    [Fact]
    public async Task External_runner_cannot_bypass_count_verification()
    {
        var error = await Assert.ThrowsAsync<ConnectorNoEffectException>(() =>
            new TeamcenterVisualizationRunner().LaunchAsync("unneeded.vvi", default));
        Assert.Equal("vismockup_document_limit_unverifiable", error.Code);
    }

    [Fact]
    public async Task Legacy_java_launch_cannot_bypass_count_verification()
    {
        var worker = new TeamcenterProcessWorker("missing-java", "missing-script", "missing-launcher", [], Path.GetTempPath());
        var error = await Assert.ThrowsAsync<ConnectorNoEffectException>(() =>
            worker.LaunchAsync(null!, "", "", "", default));
        Assert.Equal("vismockup_document_limit_unverifiable", error.Code);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Unverifiable_other_instances_only_allow_exact_existing_reuse(bool existing)
    {
        var app = new CountingApplication(1) { ScopeUnverifiable = true };
        var path = Path.GetFullPath("new.jt");
        if (existing) app.ActiveDocument = new FakeDocument("existing", path, FakeNode.FlatTree(1));
        if (existing) Assert.Same(app.ActiveDocument, VisMockupDocumentOpen.Open(app, path, 123));
        else Assert.Equal("vismockup_document_limit_unverifiable", Assert.Throws<ConnectorNoEffectException>(() =>
            VisMockupDocumentOpen.Open(app, path, 123)).Code);
        Assert.Equal(0, app.OpenCalls);
    }

    private sealed class CountingApplication(int? count) : IVisMockupApplication
    {
        private int? _count = count;
        public string ProductVersion => "14.2.0";
        public IVisMockupDocument? ActiveDocument { get; set; }
        public IReadOnlyList<IVisMockupDocument> OpenDocuments { get; set; } = [];
        public int OpenDocumentCount => _count ?? throw new InvalidOperationException("count unavailable");
        public int OpenCalls { get; private set; }
        public int OpenDelay { get; init; }
        public bool ScopeUnverifiable { get; init; }
        public void VerifyDocumentOpenScope()
        {
            if (ScopeUnverifiable) throw new InvalidOperationException("Other instance has no COM count");
        }
        public IVisMockupDocument OpenDocument(string path)
        {
            Thread.Sleep(OpenDelay);
            OpenCalls++;
            _count++;
            return ActiveDocument = new FakeDocument(path, path, FakeNode.FlatTree(1));
        }
        public void CloseAllDocuments() => throw new InvalidOperationException("Must not close documents");
    }
}
