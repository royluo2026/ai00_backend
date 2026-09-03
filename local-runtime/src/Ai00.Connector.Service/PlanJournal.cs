using System.Text.Json;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Service;

public enum PlanState { Admitted, Executing, Completed, Failed, OutcomeUnknown, Reconciled }
public enum StepState { Queued, Started, Completed, Failed, OutcomeUnknown }

public sealed record JournalRecord(
    long Sequence,
    string PlanId,
    PlanState PlanState,
    string? StepId,
    StepState? StepState,
    ConnectorExecutionPlan? Plan,
    SignedConnectorPlanOutcome? Outcome,
    DateTimeOffset RecordedAt);

public sealed record PlanReconciliation(
    string PlanId,
    PlanState State,
    SignedConnectorPlanOutcome? Outcome);

public sealed class PlanJournal
{
    private readonly object _gate = new();
    private readonly string _path;
    private readonly List<JournalRecord> _records;

    public PlanJournal(string path)
    {
        _path = Path.GetFullPath(path);
        _records = File.Exists(_path)
            ? JsonSerializer.Deserialize<List<JournalRecord>>(File.ReadAllBytes(_path)) ?? []
            : [];
    }

    public bool Admit(ConnectorExecutionPlan plan)
    {
        lock (_gate)
        {
            if (_records.Any(item => item.PlanId == plan.PlanId)) return false;
            AppendLocked(plan.PlanId, PlanState.Admitted, null, null, plan, null);
            return true;
        }
    }

    public void RecordStarted(string planId, string stepId)
    {
        lock (_gate)
        {
            RequirePlan(planId);
            AppendLocked(planId, PlanState.Executing, stepId, StepState.Started, null, null);
        }
    }

    public void RecordCompleted(string planId, SignedConnectorPlanOutcome outcome)
    {
        lock (_gate)
        {
            RequirePlan(planId);
            if (outcome.Outcome.PlanId != planId) throw new ConnectorException("plan_identity_mismatch");
            AppendLocked(planId, PlanState.Completed, null, null, null, outcome);
        }
    }

    public SignedConnectorPlanOutcome? RetainedOutcome(string planId)
    {
        lock (_gate)
            return _records.LastOrDefault(item => item.PlanId == planId && item.Outcome is not null)?.Outcome;
    }

    public PlanReconciliation? FirstUnreconciled()
    {
        lock (_gate)
        {
            foreach (var planId in _records.Select(item => item.PlanId).Distinct(StringComparer.Ordinal))
            {
                var latest = _records.Last(item => item.PlanId == planId);
                if (latest.PlanState is PlanState.Executing or PlanState.Completed or PlanState.Failed or PlanState.OutcomeUnknown)
                    return new(planId, latest.PlanState, RetainedOutcome(planId));
            }
            return null;
        }
    }

    public void MarkReconciled(string planId)
    {
        lock (_gate)
        {
            RequirePlan(planId);
            AppendLocked(planId, PlanState.Reconciled, null, null, null, null);
        }
    }

    private void RequirePlan(string planId)
    {
        if (!_records.Any(item => item.PlanId == planId))
            throw new ConnectorException("plan_not_admitted");
    }

    private void AppendLocked(
        string planId, PlanState planState, string? stepId, StepState? stepState,
        ConnectorExecutionPlan? plan, SignedConnectorPlanOutcome? outcome)
    {
        _records.Add(new(_records.Count + 1L, planId, planState, stepId, stepState, plan, outcome, DateTimeOffset.UtcNow));
        var directory = Path.GetDirectoryName(_path) ?? throw new InvalidOperationException("plan_journal_path_invalid");
        Directory.CreateDirectory(directory);
        var temporaryPath = _path + ".tmp-" + Guid.NewGuid().ToString("N");
        try
        {
            using (var stream = new FileStream(temporaryPath, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough))
            {
                JsonSerializer.Serialize(stream, _records);
                stream.Flush(true);
            }
            File.Move(temporaryPath, _path, true);
        }
        finally
        {
            if (File.Exists(temporaryPath)) File.Delete(temporaryPath);
        }
    }
}
