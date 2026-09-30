using Ai00.Connector.Adapters.VisMockup;
using Xunit;
namespace Ai00.Connector.Tests;
public sealed class LocalModelPackagesTests
{
    [Fact]
    public void Restart_preserves_live_native_references_and_expired_closed_packages_are_removed()
    {
        var root=Path.Combine(Path.GetTempPath(),"package-expiry-"+Guid.NewGuid().ToString("N"));
        var directory=Path.Combine(root,new string('a',64));Directory.CreateDirectory(directory);
        try {
            File.WriteAllText(Path.Combine(directory,"part.jt"),"geometry");LocalModelPackages.Protect(directory,123,456);
            Directory.SetLastWriteTimeUtc(directory,DateTime.UtcNow.AddDays(-8));
            LocalModelPackages.Trim(root,TimeSpan.FromDays(7),lease=>lease.ProcessId==123&&lease.Started==456);
            Assert.True(Directory.Exists(directory));
            LocalModelPackages.Trim(root,TimeSpan.FromDays(7),_=>false);Assert.False(Directory.Exists(directory));
        } finally {Directory.Delete(root,true);}
    }
}
