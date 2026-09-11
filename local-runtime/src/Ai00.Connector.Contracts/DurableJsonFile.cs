using System.Text.Json;
namespace Ai00.Connector.Contracts;

public static class DurableJsonFile
{
    public static void Write<T>(string path,T value)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)??throw new InvalidDataException("journal_path_invalid"));
        var temporary=path+".tmp-"+Guid.NewGuid().ToString("N");
        try
        {
            using(var stream=new FileStream(temporary,FileMode.CreateNew,FileAccess.Write,FileShare.None,4096,FileOptions.WriteThrough))
            {
                JsonSerializer.Serialize(stream,value);
                stream.Flush(true);
            }
            // Windows can briefly deny replacement while another in-process
            // reader or security scanner still owns a non-delete-sharing handle.
            // The temporary file is already durable, so retrying only this local
            // idempotent replace is safe; external connector actions are never
            // retried here.
            for(var attempt=0;;attempt++)
            {
                try{File.Move(temporary,path,true);break;}
                catch(Exception error) when(
                    attempt<7 &&
                    (error is IOException || error is UnauthorizedAccessException))
                {
                    Thread.Sleep(50*(attempt+1));
                }
            }
        }
        finally{if(File.Exists(temporary))File.Delete(temporary);}
    }
}
