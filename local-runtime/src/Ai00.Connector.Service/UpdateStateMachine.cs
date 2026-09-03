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

public interface IUpdateSlots
{
    Task DrainAsync(CancellationToken cancellationToken);
    Task SwitchAsync(UpdatePackage package, CancellationToken cancellationToken);
    Task RollbackAsync(CancellationToken cancellationToken);
}

public sealed class UpdateCoordinator(IUpdatePackageVerifier verifier, IUpdateSlots slots)
{
    public async Task<UpdateState> ApplyAsync(
        UpdatePackage package,
        Func<CancellationToken, Task<bool>> healthCheck,
        CancellationToken cancellationToken)
    {
        var machine = new UpdateStateMachine();
        machine.MoveTo(UpdateState.Downloading);
        try
        {
            machine.MoveTo(UpdateState.Verifying);
            verifier.RequireTrusted(package);
            machine.MoveTo(UpdateState.Draining);
            await slots.DrainAsync(cancellationToken);
            machine.MoveTo(UpdateState.Switching);
            await slots.SwitchAsync(package, cancellationToken);
            machine.MoveTo(UpdateState.HealthChecking);
            if (await healthCheck(cancellationToken))
            {
                machine.MoveTo(UpdateState.Completed);
                return machine.State;
            }
        }
        catch when (machine.State is UpdateState.Downloading or UpdateState.Verifying or UpdateState.Draining or UpdateState.Switching or UpdateState.HealthChecking)
        {
            await slots.RollbackAsync(CancellationToken.None);
            machine.MoveTo(UpdateState.RolledBack);
            return machine.State;
        }
        await slots.RollbackAsync(CancellationToken.None);
        machine.MoveTo(UpdateState.RolledBack);
        return machine.State;
    }
}
