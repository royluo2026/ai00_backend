using System.Drawing;
using System.Drawing.Imaging;
using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class ReverseCaptureRendererTests : IDisposable
{
    private readonly string _directory = Path.Combine(Path.GetTempPath(), "ai00-reverse-render", Guid.NewGuid().ToString("N"));
    private static readonly CaptureProfile Profile = new("png", 1920, 1080, "current");

    [Fact]
    public void GrayValidationSeparatesSmallCornerCoordinateOverlayFromColoredGeometry()
    {
        using var bitmap = new Bitmap(1920, 1080);
        using var graphics = Graphics.FromImage(bitmap);
        graphics.Clear(Color.White);
        graphics.FillRectangle(Brushes.Gray, 650, 400, 200, 100);
        graphics.FillRectangle(Brushes.Red, 200, 950, 150, 3);
        graphics.FillRectangle(Brushes.Lime, 200, 850, 3, 100);
        var file = Path.Combine(_directory, "coordinate-overlay.png");
        Directory.CreateDirectory(_directory);
        bitmap.Save(file, ImageFormat.Png);
        CapturePixels.Read(file, Profile).RequireGrayScene();

        graphics.FillRectangle(Brushes.Blue, 800, 400, 200, 100);
        bitmap.Save(file, ImageFormat.Png);
        Assert.Equal("capture_gray_baseline_invalid", Assert.Throws<ConnectorException>(() =>
            CapturePixels.Read(file, Profile).RequireGrayScene()).Code);

        graphics.FillRectangle(Brushes.Gray, 800, 400, 200, 100);
        graphics.FillRectangle(Brushes.Blue, 200, 850, 100, 100);
        bitmap.Save(file, ImageFormat.Png);
        Assert.Equal("capture_gray_baseline_invalid", Assert.Throws<ConnectorException>(() =>
            CapturePixels.Read(file, Profile).RequireGrayScene()).Code);
    }

    private static FakeDocument Document()
    {
        var document = new FakeDocument("document", "tc://test", new FakeNode("root", "Root", "root", "root", [
            new FakeNode("part-a", "A", "a", "a", []), new FakeNode("part-b", "B", "b", "b", []),
            new FakeNode("outside", "Other line", "outside", "outside", []),
        ]));
        document.CaptureWriter = path =>
        {
            using var image = new Bitmap(1920, 1080);
            using var graphics = Graphics.FromImage(image);
            graphics.Clear(Color.White);
            var position = 0;
            foreach (var key in new[] { "part-a", "part-b", "outside" })
            {
                if (document.IsNodeVisible(key))
                {
                    var color = document.NodeColors.GetValueOrDefault(key, (.42, .42, .42));
                    using var brush = new SolidBrush(Color.FromArgb((int)(color.Item1 * 255), (int)(color.Item2 * 255), (int)(color.Item3 * 255)));
                    graphics.FillRectangle(brush, 650 + position * 210, 410, 200, 200);
                }
                position++;
            }
            image.Save(path, ImageFormat.Png);
        };
        return document;
    }

    [Fact]
    public void GrayBlueCaptureThenHideLeavesEarlierProductsGray()
    {
        var document = Document();
        document.SetNodeVisible("outside", true);
        var state = new VisMockupSessionState();
        var scenes = new SceneController(state);
        var renderer = new ReverseCaptureRenderer(state, scenes, new InternalCapture(_directory));
        var before = SceneState.Create("op-b", ["part-a", "part-b"], [], Profile);
        renderer.Render(document, before, [], true);
        Assert.Equal(["part-a", "part-b"], document.VisibleNodeKeys.Order(StringComparer.Ordinal));
        Assert.Equal((.42, .42, .42), document.NodeColors["part-b"]);
        renderer.Render(document, before, ["part-b"], false);
        var image = renderer.Capture(document, new("run", "step", "op-b", 1, Profile));
        Assert.True(File.Exists(image.Path));
        using (var bitmap = new Bitmap(image.Path)) Assert.Equal(255, bitmap.GetPixel(900, 450).B);
        var after = SceneState.Create("op-b", ["part-a"], [], Profile);
        renderer.Render(document, after, [], false);
        Assert.True(scenes.Verify(document, "op-b", after.SceneHash).Matches);
        Assert.Equal(["part-a"], document.VisibleNodeKeys);
        Assert.Equal((.42, .42, .42), document.NodeColors["part-a"]);
        Assert.Equal((.42, .42, .42), document.NodeColors["part-b"]);
        Assert.Equal(1, document.FitCaptureCalls);
        Assert.Single(Directory.GetFiles(_directory, "*", SearchOption.AllDirectories));
    }

    [Fact]
    public void MissingBluePixelsNeverCommitOrHideTargets()
    {
        var document = Document();
        document.IgnoreNodeColors = true;
        var state = new VisMockupSessionState();
        var renderer = new ReverseCaptureRenderer(state, new SceneController(state), new InternalCapture(_directory));
        renderer.Render(document, SceneState.Create("op", ["part-a", "part-b"], [], Profile), ["part-b"], false);
        var error = Assert.Throws<ConnectorException>(() => renderer.Capture(document, new("run", "step", "op", 1, Profile)));
        Assert.Equal("capture_target_not_blue_or_occluded", error.Code);
        Assert.True(document.IsNodeVisible("part-b"));
        Assert.Empty(Directory.GetFiles(_directory, "*", SearchOption.AllDirectories));
    }

    [Fact]
    public void OutOfScopeHighlightIsRejectedBeforeAnyVisibilityChange()
    {
        var document = Document();
        var state = new VisMockupSessionState();
        var renderer = new ReverseCaptureRenderer(state, new SceneController(state), new InternalCapture(_directory));
        Assert.Throws<ConnectorException>(() => renderer.Render(document,
            SceneState.Create("op", ["part-a"], [], Profile), ["outside"], false));
        Assert.Empty(document.VisibilityChanges);
    }

    [Fact]
    public void EmptySceneIsRejectedWithoutLeavingBaselineFiles()
    {
        var document = Document();
        document.CaptureWriter = path => { using var bitmap = new Bitmap(1920, 1080); bitmap.Save(path, ImageFormat.Png); };
        var state = new VisMockupSessionState();
        var renderer = new ReverseCaptureRenderer(state, new SceneController(state), new InternalCapture(_directory));
        var error = Assert.Throws<ConnectorException>(() => renderer.Render(document,
            SceneState.Create("op", ["part-a"], [], Profile), ["part-a"], false));
        Assert.Equal("capture_empty_or_clipped_scene", error.Code);
        Assert.Empty(Directory.GetFiles(_directory));
    }

    [Fact]
    public async Task AdvertisedRenderExecutesOnlyForTheBoundDocumentAndSnapshot()
    {
        var document = Document();
        var snapshot = new DocumentSnapshotReader().Read(document, 10_000, 64);
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]),
            new FakeVisMockupCom { ExistingApplication = new FakeApplication("14.2.0", document) }, _directory);
        var scene = SceneState.Create("op", ["part-a", "part-b"], [], Profile);
        var payload = JsonSerializer.SerializeToElement(new {
            document_id = document.DocumentId, baseline_snapshot_hash = snapshot.SnapshotHash,
            operation_id = "op", highlight_products = new[] { "part-b" }, fit_all = true,
            scene = new { operation_id = "op", visible_products = scene.VisibleProducts,
                visible_resources = scene.VisibleResources, capture_profile = new { format = "png", width = 1920, height = 1080, background = "current" }, scene_hash = scene.SceneHash },
        });
        Assert.Contains(adapter.Manifest.Operations, item => item.OperationId == "vismockup.scene.render@1"
            && item.ContractHash == "sha256:0cb32eaf55dc0a4ec477878ad9a3934fcf08273f4ab6e0b78a6fa5d504c0c1e2");
        var rendered = await adapter.ExecuteAsync(new("vismockup.scene.render@1", payload, "render"), default);
        Assert.Equal(scene.SceneHash, JsonSerializer.SerializeToElement(rendered.Data).GetProperty("actual_scene_hash").GetString());
        var image = await adapter.CaptureAsync(new("run", "capture", "op", 1, Profile));
        Assert.True(File.Exists(image.Path));
    }

    [Fact]
    public async Task PlmxmlBaselineResolvesStableKeysToTheLiveSessionBeforeRendering()
    {
        var document = new FakeDocument("document", "tc://capture", new FakeNode("1", "Root", "root", "root", [
            new FakeNode("2", "Part/A", "part", "Part", []),
        ])) {
            ExportPlmxmlContent = """
                <PLMXML><InstanceGraph rootRefs="root">
                  <ProductInstance id="root" name="Root"/>
                  <ProductInstance id="child" name="Part/A"/>
                  <Occurrence instanceRefs="#root"><UserData>
                    <UserValue title="__PLM_OCC_PDM_UID" value="root-pdm"/>
                  </UserData></Occurrence>
                  <Occurrence instanceRefs="#root #child"><UserData>
                    <UserValue title="__PLM_OCC_PDM_UID" value="part-pdm"/>
                  </UserData></Occurrence>
                </InstanceGraph></PLMXML>
                """,
        };
        document.CaptureWriter = path => {
            using var bitmap = new Bitmap(1920, 1080);
            using var graphics = Graphics.FromImage(bitmap);
            graphics.Clear(Color.White);
            if (document.IsNodeVisible("2"))
            {
                var color = document.NodeColors.GetValueOrDefault("2", (.42, .42, .42));
                using var brush = new SolidBrush(Color.FromArgb((int)(color.Item1 * 255), (int)(color.Item2 * 255), (int)(color.Item3 * 255)));
                graphics.FillRectangle(brush, 650, 410, 200, 200);
            }
            bitmap.Save(path, ImageFormat.Png);
        };
        var com = new FakeVisMockupCom {
            ExistingApplication = new FakeApplication("14.2.0", document),
            ProcessId = 10, ProcessStartUtcTicks = 100,
        };
        using var sta = new StaDispatcher();
        var adapter = new VisMockupAdapter(sta, new AllowedPathPolicy([Path.GetTempPath()]),
            com, _directory, Path.Combine(_directory, "tree.db"));
        var snapshot = await adapter.SnapshotAsync(10_000, 64);
        Assert.Equal("pdm:root-pdm", snapshot.RootNodeKey);
        Assert.NotEqual(new DocumentSnapshotReader().Read(document, 10_000, 64).SnapshotHash, snapshot.SnapshotHash);
        var scene = SceneState.Create("process", ["pdm:part-pdm"], [], Profile);
        var payload = JsonSerializer.SerializeToElement(new {
            document_id = document.DocumentId, baseline_snapshot_hash = snapshot.SnapshotHash,
            operation_id = "process", highlight_products = new[] { "pdm:part-pdm" }, fit_all = true,
            scene = new { operation_id = "process", visible_products = scene.VisibleProducts,
                visible_resources = scene.VisibleResources, capture_profile = new { format = "png", width = 1920, height = 1080, background = "current" }, scene_hash = scene.SceneHash },
        });
        await adapter.ExecuteAsync(new("vismockup.scene.render@1", payload, "render"), default);
        Assert.Equal((0d, 0d, 1d), document.NodeColors["2"]);
        Assert.DoesNotContain("pdm:part-pdm", document.NodeColors.Keys);
        var image = await adapter.CaptureAsync(new("run", "capture", "process", 1, Profile));
        Assert.True(File.Exists(image.Path));
        var visibilityChanges = document.VisibilityChanges.Count;
        com.ProcessStartUtcTicks = 200;
        var error = await Assert.ThrowsAsync<ConnectorException>(() =>
            adapter.ExecuteAsync(new("vismockup.scene.render@1", payload, "stale"), default));
        Assert.Equal("vismockup_document_changed", error.Code);
        Assert.Equal(visibilityChanges, document.VisibilityChanges.Count);
        var staleCapture = await Assert.ThrowsAsync<ConnectorException>(() =>
            adapter.CaptureAsync(new("run", "stale-capture", "process", 1, Profile)));
        Assert.Equal("vismockup_document_changed", staleCapture.Code);
        var staleVerify = await Assert.ThrowsAsync<ConnectorException>(() =>
            adapter.VerifySceneAsync(document.DocumentId, "process", scene.SceneHash));
        Assert.Equal("vismockup_document_changed", staleVerify.Code);
    }

    [Fact]
    public void UnmappedStableKeyFailsBeforeChangingColorsOrVisibility()
    {
        var document = Document();
        var state = new VisMockupSessionState(resolveNode: (_, key) =>
            key == "pdm:known" ? "part-a" : throw new ConnectorException("vismockup_session_node_mapping_stale"));
        var renderer = new ReverseCaptureRenderer(state, new SceneController(state), new InternalCapture(_directory));
        var error = Assert.Throws<ConnectorException>(() => renderer.Render(document,
            SceneState.Create("process", ["pdm:known", "pdm:unknown"], [], Profile), ["pdm:known"], true));
        Assert.Equal("vismockup_session_node_mapping_stale", error.Code);
        Assert.Empty(document.VisibilityChanges);
        Assert.Empty(document.NodeColors);
    }

    [Fact]
    public void RejectedBaselineDoesNotPoisonALaterValidRequest()
    {
        var document = Document();
        var state = new VisMockupSessionState();
        Assert.Throws<ConnectorException>(() => state.RequireBaseline(document, "wrong"));
        Assert.Null(state.DocumentId);
        state.RequireBaseline(document, new DocumentSnapshotReader().Read(document, 10_000, 64).SnapshotHash);
        Assert.Equal(document.DocumentId, state.DocumentId);
    }

    [Fact]
    public void NativeImageIsAspectFittedWithoutCroppingToTheCaptureProfile()
    {
        Directory.CreateDirectory(_directory);
        var path = Path.Combine(_directory, "native.png");
        using (var native = new Bitmap(800, 400))
        {
            using var graphics = Graphics.FromImage(native);
            graphics.Clear(Color.White);
            graphics.FillRectangle(Brushes.Blue, 200, 100, 400, 200);
            native.Save(path, ImageFormat.Png);
        }
        CapturePixels.NormalizePng(path, Profile);
        using var image = new Bitmap(path);
        Assert.Equal(1920, image.Width);
        Assert.Equal(1080, image.Height);
        Assert.Equal(Color.White.ToArgb(), image.GetPixel(960, 10).ToArgb());
        Assert.Equal(Color.Blue.ToArgb(), image.GetPixel(960, 540).ToArgb());
    }

    [Fact]
    public void CaptureRunCannotEscapeItsControlledOutputDirectory()
    {
        var capture = new InternalCapture(_directory);
        var error = Assert.Throws<ConnectorException>(() => capture.Capture(Document(), new("..", "step", "op", 1, Profile)));
        Assert.Equal("capture_request_invalid", error.Code);
    }

    public void Dispose()
    {
        if (Directory.Exists(_directory)) Directory.Delete(_directory, true);
    }
}
