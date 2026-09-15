using Ai00.Connector.AppHost;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class TeamcenterControlProtocolTests
{
    [Fact]
    public void Login_is_closed_bounded_and_endpoint_allowlisted()
    {
        var command = TeamcenterControlProtocol.ParseRequest(
            """{"type":"teamcenter_login","request_id":"tc-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","endpoint_id":"tc-production","username":"user","password":"secret"}""");
        Assert.Equal("user", command.Username);
        Assert.ThrowsAny<Exception>(() => TeamcenterControlProtocol.ParseRequest(
            """{"type":"teamcenter_login","request_id":"tc-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","endpoint_id":"https://evil/","username":"u","password":"p"}"""));
        Assert.ThrowsAny<Exception>(() => TeamcenterControlProtocol.ParseRequest(
            """{"type":"teamcenter_login","request_id":"tc-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","endpoint_id":"tc-production","username":"u","password":"p","extra":true}"""));
    }

    [Fact]
    public void Result_never_contains_credentials()
    {
        var json = TeamcenterControlProtocol.Result("tc-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", true, "ready");
        Assert.DoesNotContain("username", json);
        Assert.DoesNotContain("password", json);
        Assert.Equal("teamcenter_login_result", System.Text.Json.JsonDocument.Parse(json).RootElement.GetProperty("type").GetString());
    }
}
