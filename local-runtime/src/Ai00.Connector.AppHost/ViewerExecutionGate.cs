namespace Ai00.Connector.AppHost;

// One instance spans every step of a cloud plan and every target of an interaction.
public sealed class ViewerExecutionGate
{
    private readonly SemaphoreSlim serial=new(1,1);
    private int quarantined;
    public bool IsQuarantined=>Volatile.Read(ref quarantined)!=0;
    public void Quarantine(string reason)=>Interlocked.Exchange(ref quarantined,1);
    public IDisposable? TryEnterInteractive()
    {
        if(IsQuarantined||!serial.Wait(0))return null;
        if(IsQuarantined){serial.Release();return null;}
        return new Lease(serial);
    }
    public async Task<IDisposable> EnterPlanAsync(CancellationToken ct)
    {
        if(IsQuarantined)throw new InvalidDataException("runtime_quarantined");
        await serial.WaitAsync(ct);
        if(IsQuarantined){serial.Release();throw new InvalidDataException("runtime_quarantined");}
        return new Lease(serial);
    }
    private sealed class Lease(SemaphoreSlim serial):IDisposable
    {
        private int released;
        public void Dispose(){if(Interlocked.Exchange(ref released,1)==0)serial.Release();}
    }
}
