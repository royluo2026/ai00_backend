using System.Security.Cryptography;
using System.Text;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.SessionHost;

public sealed class SingleInstanceGuard : IDisposable
{
    private readonly Mutex _mutex;
    private bool _ownsMutex;

    private SingleInstanceGuard(Mutex mutex) => (_mutex, _ownsMutex) = (mutex, true);

    public static SingleInstanceGuard Acquire(string deviceId, string windowsSid)
    {
        var identity = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(deviceId + "\n" + windowsSid))).ToLowerInvariant();
        var mutex = new Mutex(true, "Local\\AI00.Connector.SessionHost." + identity, out var createdNew);
        if (!createdNew)
        {
            mutex.Dispose();
            throw new ConnectorException("interactive_session_conflict");
        }
        return new SingleInstanceGuard(mutex);
    }

    public void Dispose()
    {
        if (_ownsMutex)
        {
            _ownsMutex = false;
            _mutex.ReleaseMutex();
        }
        _mutex.Dispose();
    }
}
