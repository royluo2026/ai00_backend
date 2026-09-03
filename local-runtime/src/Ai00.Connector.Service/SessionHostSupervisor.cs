namespace Ai00.Connector.Service;

public sealed record DeviceBinding(string DeviceId, string UserId, string WindowsSid);

public enum SessionHostState { Ready, Missing, Conflict }

public sealed record SessionHostHealth(SessionHostState State, int? SessionId = null);

public interface IWindowsSessionLocator
{
    IReadOnlyList<int> ForSid(string windowsSid);
}

public interface ISessionHostLauncher
{
    Task EnsureSessionHostAsync(int sessionId, DeviceBinding binding, CancellationToken cancellationToken);
}

public sealed class SessionHostSupervisor(
    IWindowsSessionLocator windowsSessions,
    ISessionHostLauncher launcher)
{
    public async Task<SessionHostHealth> EnsureBoundSessionAsync(
        DeviceBinding binding,
        CancellationToken cancellationToken)
    {
        var sessions = windowsSessions.ForSid(binding.WindowsSid);
        if (sessions.Count == 0) return new(SessionHostState.Missing);
        if (sessions.Count > 1) return new(SessionHostState.Conflict);
        var sessionId = sessions[0];
        await launcher.EnsureSessionHostAsync(sessionId, binding, cancellationToken);
        return new(SessionHostState.Ready, sessionId);
    }
}
