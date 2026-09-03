namespace Ai00.Connector.Service;

public sealed class UpdateStateMachine
{
    private static readonly IReadOnlyDictionary<UpdateState, UpdateState[]> Allowed = new Dictionary<UpdateState, UpdateState[]>
    {
        [UpdateState.Idle] = [UpdateState.Downloading],
        [UpdateState.Downloading] = [UpdateState.Verifying, UpdateState.RolledBack],
        [UpdateState.Verifying] = [UpdateState.Draining, UpdateState.RolledBack],
        [UpdateState.Draining] = [UpdateState.Switching, UpdateState.RolledBack],
        [UpdateState.Switching] = [UpdateState.HealthChecking, UpdateState.RolledBack],
        [UpdateState.HealthChecking] = [UpdateState.Completed, UpdateState.RolledBack],
        [UpdateState.Completed] = [UpdateState.Idle],
        [UpdateState.RolledBack] = [UpdateState.Idle],
    };
    public UpdateState State { get; private set; } = UpdateState.Idle;
    public void MoveTo(UpdateState next)
    {
        if (!Allowed[State].Contains(next)) throw new InvalidOperationException($"Invalid update transition: {State} -> {next}");
        State = next;
    }
}
