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
            File.Move(temporary,path,true);
        }
        finally{if(File.Exists(temporary))File.Delete(temporary);}
    }
}
