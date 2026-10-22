using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Ai00.Connector.Adapters.VisMockup;
using Ai00.Connector.Contracts.V2;
using Microsoft.Data.Sqlite;
namespace Ai00.Connector.AppHost;

// Only immutable identity/version pins and receipts belong here. Never persist bearer tokens or approval grants.
public sealed record CaptureDeliveryScope(string TenantId,string ActorId,string ProjectGid,string BopVersionGid,
    string BopHash,string ModelHash,string DeviceId,string DocumentSession,string CaptureRunId);
public sealed record CaptureDeliveryItem(string DeliveryId,string OperationId,string AttemptId,string SlotId,
    LocalCaptureArtifact Capture,string State,long Revision,JsonElement? ArtifactRef,JsonElement? AttachmentReceipt=null);

// Local evidence/outbox infrastructure. Cloud acceptance, authorization renewal and Craft mutation remain owner APIs.
public sealed class CaptureDeliveryQueue
{
    readonly string connectionString,captureRoot;readonly long maxPendingBytes;
    public CaptureDeliveryQueue(string databasePath,string captureRoot,long maxPendingBytes=512L*1024*1024)
    {
        if(maxPendingBytes<1)throw new ArgumentOutOfRangeException(nameof(maxPendingBytes));
        this.maxPendingBytes=maxPendingBytes;this.captureRoot=Path.GetFullPath(captureRoot).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
        var path=Path.GetFullPath(databasePath);Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        connectionString=new SqliteConnectionStringBuilder{DataSource=path,Pooling=false,DefaultTimeout=5}.ToString();
        using var db=Open();using var schema=Sql(db,null,"""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS capture_delivery_scopes(scope_hash TEXT PRIMARY KEY,scope_json TEXT NOT NULL,cancelled INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS capture_deliveries(delivery_id TEXT PRIMARY KEY,scope_hash TEXT NOT NULL,operation_id TEXT NOT NULL,attempt_id TEXT NOT NULL,slot_id TEXT NOT NULL,capture_json TEXT NOT NULL,byte_size INTEGER NOT NULL,state TEXT NOT NULL CHECK(state IN ('captured','uploaded','attached')),revision INTEGER NOT NULL,artifact_json TEXT,craft_json TEXT);
            CREATE INDEX IF NOT EXISTS capture_delivery_pending ON capture_deliveries(scope_hash,state);
            """);schema.ExecuteNonQuery();
    }
    SqliteConnection Open(){var db=new SqliteConnection(connectionString);db.Open();using var settings=Sql(db,null,"PRAGMA synchronous=FULL;");settings.ExecuteNonQuery();return db;}
    static SqliteCommand Sql(SqliteConnection db,SqliteTransaction? transaction,string text,params object?[] args)
    {var cmd=db.CreateCommand();cmd.Transaction=transaction;cmd.CommandText=text;for(var i=0;i<args.Length;i++)cmd.Parameters.AddWithValue("$p"+i,args[i]??DBNull.Value);return cmd;}
    static string Hash(string value)=>Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
    static void Require(string value){if(string.IsNullOrWhiteSpace(value)||value.Length>1024)throw new InvalidDataException("capture_delivery_identity_invalid");}
    static string ScopeHash(CaptureDeliveryScope scope){foreach(var value in new[]{scope.TenantId,scope.ActorId,scope.ProjectGid,scope.BopVersionGid,scope.BopHash,scope.ModelHash,scope.DeviceId,scope.DocumentSession,scope.CaptureRunId})Require(value);return Hash(JsonSerializer.Serialize(scope));}
    static CaptureDeliveryItem Read(SqliteDataReader row)=>new(row.GetString(0),row.GetString(1),row.GetString(2),row.GetString(3),JsonSerializer.Deserialize<LocalCaptureArtifact>(row.GetString(4))??throw new InvalidDataException("capture_delivery_corrupt"),row.GetString(5),row.GetInt64(6),row.IsDBNull(7)?null:JsonSerializer.Deserialize<JsonElement>(row.GetString(7)),row.IsDBNull(8)?null:JsonSerializer.Deserialize<JsonElement>(row.GetString(8)));
    const string Columns="delivery_id,operation_id,attempt_id,slot_id,capture_json,state,revision,artifact_json,craft_json";
    static CaptureDeliveryItem? Find(SqliteConnection db,SqliteTransaction? tx,string scope,string id){using var cmd=Sql(db,tx,"SELECT "+Columns+" FROM capture_deliveries WHERE scope_hash=$p0 AND delivery_id=$p1",scope,id);using var reader=cmd.ExecuteReader();return reader.Read()?Read(reader):null;}
    static bool Cancelled(SqliteConnection db,SqliteTransaction? tx,string scope){using var cmd=Sql(db,tx,"SELECT cancelled FROM capture_delivery_scopes WHERE scope_hash=$p0",scope);return Convert.ToInt64(cmd.ExecuteScalar()??0)!=0;}
    void Verify(LocalCaptureArtifact capture)
    {
        var path=Path.GetFullPath(capture.Path);
        if(!path.StartsWith(captureRoot,StringComparison.OrdinalIgnoreCase)||capture.MediaType!="image/png"||capture.ByteSize is <24 or >100*1024*1024||capture.Width<1||capture.Height<1)throw new InvalidDataException("capture_delivery_file_invalid");
        for(var check=path;check.Length>=captureRoot.TrimEnd(Path.DirectorySeparatorChar).Length;check=Path.GetDirectoryName(check)??"")
            if((File.GetAttributes(check)&FileAttributes.ReparsePoint)!=0)throw new InvalidDataException("capture_delivery_file_invalid");
        using var stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read);
        Span<byte> header=stackalloc byte[24];stream.ReadExactly(header);
        if(stream.Length!=capture.ByteSize||!header[..8].SequenceEqual(new byte[]{137,80,78,71,13,10,26,10})||Encoding.ASCII.GetString(header.Slice(12,4))!="IHDR"||BinaryPrimitives.ReadUInt32BigEndian(header.Slice(16,4))!=capture.Width||BinaryPrimitives.ReadUInt32BigEndian(header.Slice(20,4))!=capture.Height)throw new InvalidDataException("capture_delivery_file_invalid");
        stream.Position=0;if(Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant()!=capture.Sha256)throw new InvalidDataException("capture_delivery_integrity_failed");
    }
    public CaptureDeliveryItem Enqueue(CaptureDeliveryScope scope,string operationId,string attemptId,string slotId,LocalCaptureArtifact capture)
    {
        var pin=ScopeHash(scope);Require(operationId);Require(attemptId);Require(slotId);Verify(capture);
        var id=Hash(JsonSerializer.Serialize(new[]{pin,operationId,attemptId,slotId}));
        using var db=Open();using var tx=db.BeginTransaction(deferred:false);
        using(var cmd=Sql(db,tx,"INSERT OR IGNORE INTO capture_delivery_scopes(scope_hash,scope_json) VALUES($p0,$p1)",pin,JsonSerializer.Serialize(scope)))cmd.ExecuteNonQuery();
        if(Cancelled(db,tx,pin))throw new InvalidOperationException("capture_delivery_cancelled");
        var old=Find(db,tx,pin,id);if(old is not null){if(old.Capture!=capture)throw new InvalidDataException("capture_delivery_conflict");return old;}
        using(var size=Sql(db,tx,"SELECT COALESCE(SUM(byte_size),0) FROM capture_deliveries WHERE state<>'attached'"))
            if(Convert.ToInt64(size.ExecuteScalar())+capture.ByteSize>maxPendingBytes)throw new InvalidOperationException("capture_delivery_backpressure");
        using(var cmd=Sql(db,tx,"INSERT INTO capture_deliveries(delivery_id,scope_hash,operation_id,attempt_id,slot_id,capture_json,byte_size,state,revision) VALUES($p0,$p1,$p2,$p3,$p4,$p5,$p6,'captured',1)",id,pin,operationId,attemptId,slotId,JsonSerializer.Serialize(capture),capture.ByteSize))cmd.ExecuteNonQuery();
        tx.Commit();return new(id,operationId,attemptId,slotId,capture,"captured",1,null);
    }
    public IReadOnlyList<CaptureDeliveryItem> Pending(CaptureDeliveryScope scope)
    {var pin=ScopeHash(scope);using var db=Open();using var cmd=Sql(db,null,"SELECT "+Columns+" FROM capture_deliveries WHERE scope_hash=$p0 AND state<>'attached' AND EXISTS(SELECT 1 FROM capture_delivery_scopes WHERE scope_hash=$p0 AND cancelled=0) ORDER BY rowid",pin);using var rows=cmd.ExecuteReader();var result=new List<CaptureDeliveryItem>();while(rows.Read())result.Add(Read(rows));return result;}
    public CaptureDeliveryItem RecordUploaded(CaptureDeliveryScope scope,string id,long revision,JsonElement receipt)
    {
        var pin=ScopeHash(scope);using var db=Open();using var tx=db.BeginTransaction(deferred:false);
        var old=Find(db,tx,pin,id)??throw new InvalidOperationException("capture_delivery_scope_mismatch");
        try{if(receipt.GetProperty("media_type").GetString()!=old.Capture.MediaType||receipt.GetProperty("sha256").GetString()!=old.Capture.Sha256||receipt.GetProperty("byte_size").GetInt64()!=old.Capture.ByteSize||string.IsNullOrWhiteSpace(receipt.GetProperty("artifact_id").GetString()))throw new InvalidDataException("capture_delivery_receipt_invalid");}
        catch(Exception error) when(error is KeyNotFoundException or InvalidOperationException or FormatException){throw new InvalidDataException("capture_delivery_receipt_invalid",error);}
        if(old.State=="uploaded"&&old.ArtifactRef is { } prior&&CanonicalJsonV2.Hash(prior)==CanonicalJsonV2.Hash(receipt))return old;
        if(old.State!="captured"||old.Revision!=revision)throw new InvalidOperationException("capture_delivery_revision_conflict");
        using var cmd=Sql(db,tx,"UPDATE capture_deliveries SET state='uploaded',artifact_json=$p0,revision=revision+1 WHERE delivery_id=$p1 AND scope_hash=$p2 AND revision=$p3",receipt.GetRawText(),id,pin,revision);if(cmd.ExecuteNonQuery()!=1)throw new InvalidOperationException("capture_delivery_revision_conflict");
        tx.Commit();return old with{State="uploaded",Revision=revision+1,ArtifactRef=receipt.Clone()};
    }
    // This records an actual Craft acknowledgement; it does not itself attach an image.
    public CaptureDeliveryItem RecordAttached(CaptureDeliveryScope scope,string id,long revision,JsonElement receipt)
    {
        var pin=ScopeHash(scope);using var db=Open();using var tx=db.BeginTransaction(deferred:false);
        if(Cancelled(db,tx,pin))throw new InvalidOperationException("capture_delivery_cancelled");
        var old=Find(db,tx,pin,id)??throw new InvalidOperationException("capture_delivery_scope_mismatch");
        try
        {
            if(string.IsNullOrWhiteSpace(receipt.GetProperty("screenshot_gid").GetString())||
                receipt.GetProperty("bop_version_gid").GetString()!=scope.BopVersionGid||
                receipt.GetProperty("operation_id").GetString()!=old.OperationId||
                receipt.GetProperty("capture_run_id").GetString()!=scope.CaptureRunId||
                old.ArtifactRef is null||CanonicalJsonV2.Hash(receipt.GetProperty("artifact_ref"))!=CanonicalJsonV2.Hash(old.ArtifactRef.Value))
                throw new InvalidDataException("capture_delivery_craft_receipt_invalid");
        }
        catch(Exception error) when(error is KeyNotFoundException or InvalidOperationException or FormatException)
        {throw new InvalidDataException("capture_delivery_craft_receipt_invalid",error);}
        if(old.State=="attached")return old;
        if(old.State!="uploaded"||old.Revision!=revision)throw new InvalidOperationException("capture_delivery_revision_conflict");
        using var cmd=Sql(db,tx,"UPDATE capture_deliveries SET state='attached',revision=revision+1,craft_json=$p3 WHERE delivery_id=$p0 AND scope_hash=$p1 AND revision=$p2",id,pin,revision,receipt.GetRawText());if(cmd.ExecuteNonQuery()!=1)throw new InvalidOperationException("capture_delivery_revision_conflict");
        tx.Commit();return old with{State="attached",Revision=revision+1,AttachmentReceipt=receipt.Clone()};
    }
    public void Cancel(CaptureDeliveryScope scope){var pin=ScopeHash(scope);using var db=Open();using var cmd=Sql(db,null,"INSERT INTO capture_delivery_scopes(scope_hash,scope_json,cancelled) VALUES($p0,$p1,1) ON CONFLICT(scope_hash) DO UPDATE SET cancelled=1",pin,JsonSerializer.Serialize(scope));cmd.ExecuteNonQuery();}
}
