using System.Globalization;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using Ai00.Connector.Contracts;

namespace Ai00.Connector.Adapters.VisMockup;

public sealed record NativeDocumentWindow(string DocumentWindow,string WindowToken)
{
    private const string Property="AI00.Connector.ViewDocument";
    private const uint WmMdiActivate=0x0222;
    private const uint WmMdiGetActive=0x0229;
    private const uint SmtoAbortIfHung=0x0002;
    private const uint SmtoBlock=0x0001;
    private delegate bool EnumCallback(nint window,nint state);
    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumCallback callback,nint state);
    [DllImport("user32.dll")] private static extern bool EnumChildWindows(nint parent,EnumCallback callback,nint state);
    [DllImport("user32.dll")] private static extern nint GetParent(nint window);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(nint window,out uint pid);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] private static extern int GetClassName(nint window,StringBuilder value,int count);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] private static extern nint GetProp(nint window,string name);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] private static extern bool SetProp(nint window,string name,nint value);
    [DllImport("user32.dll",SetLastError=true)] private static extern nint SendMessageTimeout(
        nint window,uint message,nint wparam,nint lparam,uint flags,uint timeout,out nint result);

    private static string Class(nint window){var text=new StringBuilder(256);GetClassName(window,text,text.Capacity);return text.ToString();}
    private static bool OwnedDocument(nint window,int pid)=>window!=0&&GetWindowThreadProcessId(window,out var owner)!=0
        &&owner==pid&&Class(GetParent(window))=="MDIClient";

    internal static NativeDocumentWindow CaptureActive(
        int pid,string expectedDocumentId,Func<string> activeDocumentId,NativeDocumentWindow? previous) =>
        CaptureActiveCore(pid,expectedDocumentId,activeDocumentId,ActiveMdiChildren,OwnedDocument,
            (window,name)=>GetProp(window,name),(window,name,value)=>SetProp(window,name,value),previous);

    internal static NativeDocumentWindow Activate(
        int pid,string expectedDocumentId,Func<string> activeDocumentId,NativeDocumentWindow target) =>
        ActivateCore(pid,expectedDocumentId,activeDocumentId,target,OwnedDocument,
            (window,name)=>GetProp(window,name),ActivateAndRead);

    internal static NativeDocumentWindow FindAndCapture(int pid,string expectedDocumentId,Func<string> activeDocumentId) =>
        FindAndCaptureCore(pid,expectedDocumentId,activeDocumentId,AllMdiChildren,OwnedDocument,
            ActivateAndRead,()=>ActiveMdiChildren(pid).SingleOrDefault(),
            (window,name)=>GetProp(window,name),(window,name,value)=>SetProp(window,name,value));

    internal static NativeDocumentWindow FindAndCaptureCore(
        int pid,string expectedDocumentId,Func<string> activeDocumentId,
        Func<int,IReadOnlyList<nint>> mdiChildren,Func<nint,int,bool> ownedDocument,
        Func<nint,nint> activateAndRead,Func<nint> currentWindow,
        Func<nint,string,nint> getProperty,Func<nint,string,nint,bool> setProperty)
    {
        var previous=currentWindow();
        var candidates=mdiChildren(pid).Distinct().Where(window=>ownedDocument(window,pid)).ToArray();
        try
        {
            foreach(var window in candidates)
            {
                if(activateAndRead(window)!=window)continue;
                var before=activeDocumentId();
                var after=activeDocumentId();
                if(before!=expectedDocumentId||after!=expectedDocumentId)continue;
                var marker=NewMarker();
                if(!setProperty(window,Property,marker)||!ownedDocument(window,pid)
                    ||getProperty(window,Property)!=marker||activeDocumentId()!=expectedDocumentId)
                    throw new ConnectorException("vismockup_document_window_changed");
                return new(window.ToInt64().ToString(CultureInfo.InvariantCulture),
                    marker.ToInt64().ToString(CultureInfo.InvariantCulture));
            }
            throw new ConnectorNoEffectException("document_session_changed");
        }
        catch
        {
            if(previous!=0&&ownedDocument(previous,pid))activateAndRead(previous);
            throw;
        }
    }

    internal static NativeDocumentWindow CaptureActiveCore(
        int pid,string expectedDocumentId,Func<string> activeDocumentId,
        Func<int,IReadOnlyList<nint>> activeMdiChildren,Func<nint,int,bool> ownedDocument,
        Func<nint,string,nint> getProperty,Func<nint,string,nint,bool> setProperty,
        NativeDocumentWindow? previous)
    {
        var before=activeDocumentId();
        var candidates=activeMdiChildren(pid).Distinct().ToArray();
        var after=activeDocumentId();
        if(!string.Equals(before,expectedDocumentId,StringComparison.Ordinal)
            ||!string.Equals(after,expectedDocumentId,StringComparison.Ordinal))
            throw new ConnectorNoEffectException("document_session_changed");
        if(candidates.Length!=1||!ownedDocument(candidates[0],pid))
            throw new ConnectorException("vismockup_document_window_unavailable");
        var window=candidates[0];
        if(previous is not null&&TryParse(previous,out var oldWindow,out var oldMarker)
            &&oldWindow==window&&ownedDocument(oldWindow,pid)&&getProperty(oldWindow,Property)==oldMarker)
            return previous;
        var marker=NewMarker();
        if(!setProperty(window,Property,marker))
            throw new ConnectorException("vismockup_document_window_unavailable");
        if(!ownedDocument(window,pid)||getProperty(window,Property)!=marker)
            throw new ConnectorException("vismockup_document_window_changed");
        return new(window.ToInt64().ToString(CultureInfo.InvariantCulture),
            marker.ToInt64().ToString(CultureInfo.InvariantCulture));
    }

    internal static NativeDocumentWindow ActivateCore(
        int pid,string expectedDocumentId,Func<string> activeDocumentId,NativeDocumentWindow target,
        Func<nint,int,bool> ownedDocument,Func<nint,string,nint> getProperty,
        Func<nint,nint> activateAndRead)
    {
        if(!TryParse(target,out var window,out var marker)||!ownedDocument(window,pid)
            ||getProperty(window,Property)!=marker)
            throw new ConnectorException("vismockup_document_window_changed");
        if(activateAndRead(window)!=window)
            throw new ConnectorException("vismockup_document_window_changed");
        var before=activeDocumentId();
        var after=activeDocumentId();
        if(!string.Equals(before,expectedDocumentId,StringComparison.Ordinal)
            ||!string.Equals(after,expectedDocumentId,StringComparison.Ordinal))
            throw new ConnectorNoEffectException("document_session_changed");
        if(!ownedDocument(window,pid)||getProperty(window,Property)!=marker)
            throw new ConnectorException("vismockup_document_window_changed");
        return target;
    }

    private static IReadOnlyList<nint> ActiveMdiChildren(int pid)
    {
        var mdiClients=new HashSet<nint>();
        EnumWindows((top,_)=> {
            if(GetWindowThreadProcessId(top,out var owner)==0||owner!=pid)return true;
            EnumChildWindows(top,(child,__)=> {
                if(Class(child)=="MDIClient"&&GetWindowThreadProcessId(child,out var childOwner)!=0&&childOwner==pid)
                    mdiClients.Add(child);
                return true;
            },0);
            return true;
        },0);
        var active=new List<nint>();
        foreach(var mdi in mdiClients)
            if(SendMessageTimeout(mdi,WmMdiGetActive,0,0,SmtoAbortIfHung|SmtoBlock,250,out var child)!=0
                &&child!=0&&GetParent(child)==mdi)
                active.Add(child);
        return active;
    }

    private static IReadOnlyList<nint> AllMdiChildren(int pid)
    {
        var children=new List<nint>();
        EnumWindows((top,_)=>{
            if(GetWindowThreadProcessId(top,out var owner)==0||owner!=pid)return true;
            EnumChildWindows(top,(child,__)=>{
                if(Class(child)=="MDIClient"&&GetWindowThreadProcessId(child,out var childOwner)!=0&&childOwner==pid)
                    EnumChildWindows(child,(window,___)=>{if(GetParent(window)==child)children.Add(window);return true;},0);
                return true;
            },0);
            return true;
        },0);
        return children;
    }

    private static nint ActivateAndRead(nint window)
    {
        var mdi=GetParent(window);
        if(mdi==0||Class(mdi)!="MDIClient")return 0;
        if(SendMessageTimeout(mdi,WmMdiActivate,window,0,SmtoAbortIfHung|SmtoBlock,250,out _)==0)return 0;
        return SendMessageTimeout(mdi,WmMdiGetActive,0,0,SmtoAbortIfHung|SmtoBlock,250,out var active)==0?0:active;
    }

    private static bool TryParse(NativeDocumentWindow target,out nint window,out nint marker)
    {
        long handle=0,token=0;
        var valid=long.TryParse(target.DocumentWindow,NumberStyles.None,CultureInfo.InvariantCulture,out handle)
            &&handle>0&&long.TryParse(target.WindowToken,NumberStyles.None,CultureInfo.InvariantCulture,out token)&&token>0;
        window=(nint)handle;marker=(nint)token;return valid;
    }

    private static nint NewMarker()
    {
        var marker=(long)(BitConverter.ToUInt64(RandomNumberGenerator.GetBytes(8))&0x7fffffffffffffffUL);
        return (nint)(marker==0?1:marker);
    }
}
