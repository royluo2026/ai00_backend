using System.Text;
using System.Text.Json;
using Ai00.Connector.Contracts.V2;
namespace Ai00.Connector.AppHost;

public sealed record ViewerInteractionRequest(JsonElement Document)
{
    public string Type=>Document.GetProperty("type").GetString()!;
    public string RequestId=>Document.GetProperty("request_id").GetString()!;
    public string InteractionId=>Document.TryGetProperty("interaction_id",out var value)?value.GetString()!:"";
    public string Digest=>CanonicalJsonV2.Hash(Document);
}
public sealed record ViewerInteractionResponse(string request_id,string status,object? result=null,string? error_code=null,object? timings=null);

public static class ViewerInteractionProtocol
{
    public const int MaximumBytes=65536;
    public static ViewerInteractionRequest ParseRequest(string json)
    {
        try{return ParseCore(json);}
        catch(Exception error) when(error is InvalidOperationException or KeyNotFoundException or FormatException or OverflowException)
        {throw new InvalidDataException("interaction_request_invalid",error);}
    }
    private static ViewerInteractionRequest ParseCore(string json)
    {
        if(Encoding.UTF8.GetByteCount(json)>MaximumBytes)throw new InvalidDataException("interaction_frame_too_large");
        var value=CanonicalJsonV2.Parse(json);
        var type=ProtocolV2Schema.Text(value,"type");
        var fields=type switch{
            "install_grant"=>"grant", "resolve_nodes"=>"interaction_id source_nodes",
            "execute"=>"interaction_id sequence structure_epoch operation_id targets arguments",
            "query_request"=>"interaction_id queried_request_id", "close"=>"interaction_id",
            "prepare_document"=>"interaction_id", "activate_document"=>"interaction_id",
            _=>throw new InvalidDataException("interaction_message_forbidden")};
        ProtocolV2Schema.Closed(value,"type request_id "+fields);
        ProtocolV2Schema.Text(value,"request_id","[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}");
        if(type!="install_grant")Text(value,"interaction_id");
        if(type=="install_grant" && value.GetProperty("grant").ValueKind!=JsonValueKind.Object)throw new InvalidDataException("grant_invalid");
        if(type=="query_request")ProtocolV2Schema.Text(value,"queried_request_id","[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,255}");
        if(type=="resolve_nodes")
        {
            var nodes=Array(value,"source_nodes");var ids=new HashSet<string>();
            foreach(var node in nodes.EnumerateArray())
            {
                var kind=Text(node,"kind");
                ProtocolV2Schema.Closed(node,kind switch{"single_part_root" or "document_root"=>"source_node_id kind","occurrence_path"=>"source_node_id kind occurrence_path",_=>throw new InvalidDataException("source_node_kind_invalid")});
                if(!ids.Add(Text(node,"source_node_id")))throw new InvalidDataException("duplicate_source_node");
                if(kind=="occurrence_path")foreach(var edge in Array(node,"occurrence_path").EnumerateArray())
                {ProtocolV2Schema.Closed(edge,"occurrence_uid item_revision_uid");Text(edge,"occurrence_uid");Text(edge,"item_revision_uid");}
            }
        }
        if(type=="execute")
        {
            foreach(var name in new[]{"sequence","structure_epoch"})
                if(!value.GetProperty(name).TryGetInt64(out var number)||number is <1 or >9007199254740991)throw new InvalidDataException("interaction_integer_invalid");
            var targets=Array(value,"targets");var seen=new HashSet<string>();
            foreach(var target in targets.EnumerateArray())
                if(target.ValueKind!=JsonValueKind.String||!System.Text.RegularExpressions.Regex.IsMatch(target.GetString()!,"\\A[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}\\z")||!seen.Add(target.GetString()!))throw new InvalidDataException("interaction_target_invalid");
            var arguments=value.GetProperty("arguments");ProtocolV2Schema.Closed(arguments,"action");
            var action=Text(arguments,"action");var operation=Text(value,"operation_id");
            if(!((operation=="vismockup.node.visibility.change@1" && action is "show" or "hide") || (operation=="vismockup.node.selection.change@1" && action is "highlight" or "unhighlight")))throw new InvalidDataException("interaction_operation_forbidden");
        }
        return new(value);
    }
    private static string Text(JsonElement value,string name)
    {
        var text=ProtocolV2Schema.Text(value,name);
        if(text.Length is <1 or >256||text.Any(char.IsControl))throw new InvalidDataException("interaction_text_invalid");return text;
    }
    private static JsonElement Array(JsonElement value,string name)
    {
        var array=value.GetProperty(name);
        if(array.ValueKind!=JsonValueKind.Array||array.GetArrayLength() is <1 or >256)throw new InvalidDataException("interaction_batch_invalid");return array;
    }
    public static async Task<string> ReadFrameAsync(Stream stream,CancellationToken ct)
    {
        var bytes=new byte[MaximumBytes];var one=new byte[1];var length=0;
        while(true)
        {
            if(await stream.ReadAsync(one,ct)==0)throw new EndOfStreamException();
            if(one[0]==10)return new UTF8Encoding(false,true).GetString(bytes,0,length);
            if(length==MaximumBytes)throw new InvalidDataException("interaction_frame_too_large");
            bytes[length++]=one[0];
        }
    }
}
