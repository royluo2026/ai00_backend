using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

internal static class VisMockupDocumentOpen
{
    internal const int MaximumDocuments = 10;
    // Session-wide, including separate connector processes. Native/manual opens
    // do not participate in this lock and cannot be controlled by AI00.
    private const string MutexName = @"Local\AI00.VisMockup.DocumentOpen";

    internal static IVisMockupDocument Open(IVisMockupApplication application, string path,
        int? processId, Func<IVisMockupDocument>? create = null)
    {
        using var gate = new Mutex(false, MutexName);
        var acquired = false;
        try
        {
            try { acquired = gate.WaitOne(TimeSpan.FromMinutes(3)); }
            catch (AbandonedMutexException) { acquired = true; }
            if (!acquired) throw PreflightFailure("lock_timeout", processId);
            int count;
            try { count = application.OpenDocumentCount; }
            catch (Exception error)
            {
                throw PreflightFailure("count_read", processId, error);
            }
            if (count < 0) throw PreflightFailure("count_invalid", processId);
            if (count >= MaximumDocuments)
                return ReuseExisting(application, path, processId)
                    ?? throw new ConnectorNoEffectException("vismockup_document_limit_exceeded");
            try { application.VerifyDocumentOpenScope(); }
            catch (Exception error)
            {
                return ReuseExisting(application, path, processId)
                    ?? throw PreflightFailure("scope_read", processId, error);
            }
            return create is null ? application.OpenDocument(path) : create();
        }
        finally { if (acquired) gate.ReleaseMutex(); }
    }

    private static ConnectorNoEffectException PreflightFailure(string stage, int? processId, Exception? cause = null)
    {
        var error = new ConnectorNoEffectException("vismockup_document_limit_unverifiable");
        error.Data["preflight_stage"] = stage;
        Console.Error.WriteLine("AI00_DOCUMENT_PREFLIGHT_FAILED:" + System.Text.Json.JsonSerializer.Serialize(new
        {
            stage, process_id = processId, error_type = cause?.GetType().Name,
            error_code = cause is ConnectorException native ? native.Code :
                cause is ConnectorNoEffectException rejected ? rejected.Code : null,
            hresult = cause?.HResult
        }));
        return error;
    }

    private static IVisMockupDocument? ReuseExisting(IVisMockupApplication application, string path, int? processId)
    {
        var expected = Path.GetFullPath(path);
        var source = string.Equals(Path.GetExtension(path), ".vvi", StringComparison.OrdinalIgnoreCase)
            ? TeamcenterVisualizationSource.ReadMaterial(path) : null;
        bool Matches(IVisMockupDocument document) =>
            // A live DirectModel UID may identify only its dataset, not the
            // selected named-reference file. Do not infer that file for reuse.
            (source?.RequiresNewDocument != true || Path.IsPathFullyQualified(document.SourceIdentity))
            && WindowsVisMockupCom.MatchesOpenedSource(document, expected, source);
        var active = application.ActiveDocument;
        if (active is not null && Matches(active)) return active;
        if (processId is not > 0) return null;
        var matches = application.OpenDocuments.Where(Matches).Take(2).ToArray();
        if (matches.Length != 1) return null;
        var existing = matches[0];
        existing.SelectExistingNativeWindow(processId.Value);
        active = application.ActiveDocument;
        if (active is null || active.DocumentId != existing.DocumentId ||
            !Matches(active))
            throw new ConnectorException("vismockup_document_identity_changed");
        return active;
    }
}
