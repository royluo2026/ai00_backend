using Ai00.Connector.AppHost;
using Xunit;

namespace Ai00.Connector.Tests;

public sealed class TeamcenterControlProtocolTests
{
    [Fact]
    public void Login_is_closed_bounded_and_endpoint_allowlisted()
    {
        var command = Assert.IsType<TeamcenterLoginCommand>(TeamcenterControlProtocol.ParseRequest(
            """{"type":"teamcenter_login","request_id":"tc-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","endpoint_id":"tc-production","username":"user","password":"secret"}"""));
        Assert.Equal("user", command.Username);
        Assert.ThrowsAny<Exception>(() => TeamcenterControlProtocol.ParseRequest(
            """{"type":"teamcenter_login","request_id":"tc-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","endpoint_id":"https://evil/","username":"u","password":"p"}"""));
        Assert.ThrowsAny<Exception>(() => TeamcenterControlProtocol.ParseRequest(
            """{"type":"teamcenter_login","request_id":"tc-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","endpoint_id":"tc-production","username":"u","password":"p","extra":true}"""));
    }

    [Fact]
    public void Status_and_logout_are_closed_parameterless_commands()
    {
        var status = Assert.IsType<TeamcenterStatusCommand>(TeamcenterControlProtocol.ParseRequest(
            """{"type":"teamcenter_status","request_id":"tc-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}"""));
        var logout = Assert.IsType<TeamcenterLogoutCommand>(TeamcenterControlProtocol.ParseRequest(
            """{"type":"teamcenter_logout","request_id":"tc-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}"""));

        Assert.Equal("tc-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", status.RequestId);
        Assert.Equal("tc-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", logout.RequestId);
        Assert.ThrowsAny<Exception>(() => TeamcenterControlProtocol.ParseRequest(
            """{"type":"teamcenter_status","request_id":"tc-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","password":"secret"}"""));
    }

    [Fact]
    public void Result_never_contains_credentials()
    {
        var json = TeamcenterControlProtocol.Result("tc-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", true, "ready");
        Assert.DoesNotContain("username", json);
        Assert.DoesNotContain("password", json);
        Assert.Equal("teamcenter_login_result", System.Text.Json.JsonDocument.Parse(json).RootElement.GetProperty("type").GetString());
    }

    [Fact]
    public void Session_result_contains_only_closed_non_secret_status()
    {
        var json = TeamcenterControlProtocol.SessionResult(
            "tc-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "ready", "ready", "u***r");
        using var document = System.Text.Json.JsonDocument.Parse(json);

        Assert.Equal("teamcenter_session_result", document.RootElement.GetProperty("type").GetString());
        Assert.Equal("u***r", document.RootElement.GetProperty("masked_username").GetString());
        Assert.DoesNotContain("password", json);
    }
}
