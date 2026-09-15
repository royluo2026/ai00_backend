#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <objbase.h>
#include <oleauto.h>
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <unordered_set>
#include <vector>

namespace {
constexpr ULONG_PTR ObjectVtableRva = 0xedcf8;
constexpr ULONG_PTR InterfaceRvas[] = {0xedc20, 0xedc50, 0xedc98, 0xedcc0};
const IID AhManagerIid = {0xe78924aa,0xbb6b,0x4220,{0xb1,0x12,0xf7,0x59,0x30,0x3a,0x8b,0x46}};
const IID DocumentIid = {0x4c5b1e7b,0x279d,0x11d1,{0xad,0x40,0x00,0x60,0xb0,0x1a,0xee,0x42}};

struct AhManager : IUnknown {
    virtual HRESULT STDMETHODCALLTYPE CreateEmptyAltHier(const char *, IUnknown **) = 0;
    virtual HRESULT STDMETHODCALLTYPE GetAltHiers(UINT *, IUnknown **) = 0;
    virtual HRESULT STDMETHODCALLTYPE FindAltHierByObjGUID(const GUID *, IUnknown **) = 0;
    virtual HRESULT STDMETHODCALLTYPE AddAltHier(IUnknown *) = 0;
    virtual HRESULT STDMETHODCALLTYPE RemoveAltHier(IUnknown *) = 0;
};

struct Request { std::string source; unsigned start=0, page=0, maxNodes=0; std::wstring response; };
HMODULE selfModule{};
HHOOK messageHook{};
std::atomic<bool> completed{false};
std::atomic<bool> writeSucceeded{false};
Request request;

std::string utf8(const wchar_t *value) {
    if (!value) return {};
    int size=WideCharToMultiByte(CP_UTF8,0,value,-1,nullptr,0,nullptr,nullptr);
    std::string out(size > 0 ? static_cast<size_t>(size) : 0,'\0');
    if (size > 1) { WideCharToMultiByte(CP_UTF8,0,value,-1,out.data(),size,nullptr,nullptr); out.pop_back(); }
    return out;
}

std::wstring wide(const std::string &value) {
    int size=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,value.data(),static_cast<int>(value.size()),nullptr,0);
    std::wstring out(size > 0 ? static_cast<size_t>(size) : 0,L'\0');
    if(size>0) MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,value.data(),static_cast<int>(value.size()),out.data(),size);
    return out;
}

std::string json(const std::string &value) {
    std::ostringstream out; out << '"';
    for (unsigned char c : value) switch(c) {
        case '"': out << "\\\""; break; case '\\': out << "\\\\"; break;
        case '\b': out << "\\b"; break; case '\f': out << "\\f"; break;
        case '\n': out << "\\n"; break; case '\r': out << "\\r"; break;
        case '\t': out << "\\t"; break;
        default: if (c < 0x20) { char b[7]; std::snprintf(b,sizeof(b),"\\u%04x",c); out << b; } else out << c;
    }
    out << '"'; return out.str();
}

std::string printableName(IUnknown *ps, ULONG key) {
    auto v=*reinterpret_cast<void ***>(ps);
    using Name=HRESULT(WINAPI *)(void *,ULONG,ULONG *,char *);
    ULONG size=0;
    HRESULT hr=reinterpret_cast<Name>(v[14])(ps,key,&size,nullptr);
    if (FAILED(hr) || size == 0 || size > 1024*1024) size=4096;
    std::vector<char> buffer(size+1,0); ULONG capacity=static_cast<ULONG>(buffer.size());
    hr=reinterpret_cast<Name>(v[14])(ps,key,&capacity,buffer.data());
    return SUCCEEDED(hr) ? std::string(buffer.data()) : std::string();
}

std::string documentSource(IUnknown *aggregate) {
    IUnknown *doc=nullptr;
    if (FAILED(aggregate->QueryInterface(DocumentIid,reinterpret_cast<void **>(&doc))) || !doc) return {};
    auto v=*reinterpret_cast<void ***>(doc); BSTR value=nullptr;
    using FullName=HRESULT(WINAPI *)(void *,BSTR *);
    HRESULT hr=reinterpret_cast<FullName>(v[9])(doc,&value);
    std::string result=SUCCEEDED(hr) ? utf8(value) : std::string();
    if (value) SysFreeString(value); doc->Release(); return result;
}

std::vector<ULONG_PTR> candidates() {
    std::vector<ULONG_PTR> result;
    auto base=reinterpret_cast<ULONG_PTR>(GetModuleHandleA("Vis3D.dll"));
    if (!base) return result;
    SYSTEM_INFO si{}; GetSystemInfo(&si);
    auto at=reinterpret_cast<ULONG_PTR>(si.lpMinimumApplicationAddress);
    auto end=reinterpret_cast<ULONG_PTR>(si.lpMaximumApplicationAddress);
    while (at < end) {
        MEMORY_BASIC_INFORMATION info{};
        if (!VirtualQuery(reinterpret_cast<void *>(at),&info,sizeof(info))) break;
        auto region=reinterpret_cast<ULONG_PTR>(info.BaseAddress);
        const DWORD access=info.Protect & 0xff;
        if (info.State==MEM_COMMIT && info.Type==MEM_PRIVATE &&
            (access==PAGE_READWRITE || access==PAGE_EXECUTE_READWRITE) && !(info.Protect & PAGE_GUARD)) {
            auto words=reinterpret_cast<ULONG_PTR *>(region);
            const size_t count=info.RegionSize/sizeof(ULONG_PTR);
            for (size_t i=0;i+12<count;++i) {
                if (words[i]!=base+ObjectVtableRva) continue;
                bool match=true; for (int j=0;j<4;++j) if(words[i+2+j]!=base+InterfaceRvas[j]) match=false;
                if(match && words[i+6]) result.push_back(reinterpret_cast<ULONG_PTR>(&words[i]));
            }
        }
        ULONG_PTR next=region+info.RegionSize; if(next<=at) break; at=next;
    }
    return result;
}

struct Node { ULONG key{}, parent{}; unsigned order{}; std::string name; ULONG mapping{}; };

std::string readPage() {
    AhManager *selected=nullptr; std::string selectedSource; unsigned matches=0;
    for (auto address : candidates()) {
        auto aggregate=reinterpret_cast<IUnknown *>(address);
        auto source=documentSource(reinterpret_cast<IUnknown *>(reinterpret_cast<ULONG_PTR *>(address)[6]));
        if (source != request.source) continue;
        AhManager *manager=nullptr;
        if (SUCCEEDED(aggregate->QueryInterface(AhManagerIid,reinterpret_cast<void **>(&manager))) && manager) {
            ++matches; if(!selected) { selected=manager; selectedSource=source; } else manager->Release();
        }
    }
    if (matches!=1 || !selected) return "{\"status\":\"document_identity_ambiguous\"}";
    UINT total=0; HRESULT hr=selected->GetAltHiers(&total,nullptr);
    if (FAILED(hr) || total>1000000) { selected->Release(); return "{\"status\":\"hierarchy_manager_failed\"}"; }
    std::vector<IUnknown *> items(total,nullptr);
    if(total && FAILED(selected->GetAltHiers(&total,items.data()))) { selected->Release(); return "{\"status\":\"hierarchy_manager_failed\"}"; }
    std::ostringstream out; out << "{\"status\":\"ok\",\"source_identity\":" << json(selectedSource)
        << ",\"total_hierarchies\":" << total << ",\"hierarchies\":[";
    unsigned used=0; bool firstHierarchy=true;
    const unsigned stop=std::min<unsigned>(total,request.start+request.page);
    for(unsigned index=request.start; index<stop && used<request.maxNodes; ++index) {
        IUnknown *ps=items[index]; if(!ps) continue;
        auto v=*reinterpret_cast<void ***>(ps);
        using Root=HRESULT(WINAPI *)(void *,ULONG *);
        using Pair=HRESULT(WINAPI *)(void *,ULONG,ULONG *);
        using Child=HRESULT(WINAPI *)(void *,ULONG,ULONG,ULONG *);
        ULONG root=0; if(FAILED(reinterpret_cast<Root>(v[3])(ps,&root))) continue;
        std::vector<Node> nodes; std::vector<ULONG> pending{root}; std::unordered_set<ULONG> seen;
        bool complete=true;
        for(size_t cursor=0;cursor<pending.size();++cursor) {
            if(used>=request.maxNodes) { complete=false; break; }
            ULONG key=pending[cursor]; if(!seen.insert(key).second) continue;
            ULONG parent=0,mapping=0,count=0;
            reinterpret_cast<Pair>(v[8])(ps,key,&parent);
            reinterpret_cast<Pair>(v[29])(ps,key,&mapping);
            reinterpret_cast<Pair>(v[5])(ps,key,&count);
            unsigned order=0;
            if(parent) {
                ULONG siblings=0; reinterpret_cast<Pair>(v[5])(ps,parent,&siblings);
                for(ULONG j=0;j<siblings;++j) { ULONG child=0; if(SUCCEEDED(reinterpret_cast<Child>(v[6])(ps,parent,j,&child))&&child==key){order=j;break;} }
            }
            nodes.push_back({key,parent,order,printableName(ps,key),mapping}); ++used;
            for(ULONG j=0;j<count;++j) { ULONG child=0; if(SUCCEEDED(reinterpret_cast<Child>(v[6])(ps,key,j,&child))&&child) pending.push_back(child); }
        }
        if(!firstHierarchy) out << ','; firstHierarchy=false;
        out << "{\"native_index\":" << (index+1) << ",\"name\":" << json(printableName(ps,root))
            << ",\"complete\":" << (complete?"true":"false") << ",\"nodes\":[";
        for(size_t n=0;n<nodes.size();++n) {
            if(n) out << ','; const auto &node=nodes[n];
            const std::string key="ah:"+std::to_string(index+1)+":"+std::to_string(node.key);
            out << "{\"node_key\":" << json(key) << ",\"parent_key\":";
            if(node.parent) out << json("ah:"+std::to_string(index+1)+":"+std::to_string(node.parent)); else out << "null";
            out << ",\"child_order\":" << node.order << ",\"name\":" << json(node.name)
                << ",\"occurrence_id\":" << json("aps:"+std::to_string(node.key))
                << ",\"product_ref\":" << json(node.mapping?"cps:"+std::to_string(node.mapping):"") << '}';
        }
        out << "]}";
    }
    for(auto item:items) if(item) item->Release(); selected->Release();
    out << "]}"; return out.str();
}

bool writeResponse(const std::string &body) {
    auto temp=request.response+L".tmp";
    HANDLE file=CreateFileW(temp.c_str(),GENERIC_WRITE,0,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE) return false;
    DWORD written=0; bool ok=WriteFile(file,body.data(),static_cast<DWORD>(body.size()),&written,nullptr) && written==body.size();
    if(ok) ok=FlushFileBuffers(file); CloseHandle(file);
    if(ok) ok=MoveFileExW(temp.c_str(),request.response.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
    if(!ok) DeleteFileW(temp.c_str());
    return ok;
}

LRESULT CALLBACK onMessage(int code,WPARAM wp,LPARAM lp) {
    if(code>=0 && !completed.exchange(true)) writeSucceeded=writeResponse(readPage());
    return CallNextHookEx(messageHook,code,wp,lp);
}

BOOL CALLBACK findWindow(HWND hwnd,LPARAM value) {
    DWORD pid=0; GetWindowThreadProcessId(hwnd,&pid);
    if(pid==GetCurrentProcessId() && IsWindowVisible(hwnd) && !GetWindow(hwnd,GW_OWNER)) {
        *reinterpret_cast<HWND *>(value)=hwnd; return FALSE;
    }
    return TRUE;
}

bool readRequest(const wchar_t *path) {
    std::ifstream input(path,std::ios::binary); std::string source,response;
    if(!std::getline(input,source) || !std::getline(input,response)) return false;
    input >> request.start >> request.page >> request.maxNodes;
    request.source=source; request.response=wide(response);
    return !request.source.empty() && !request.response.empty() && request.page>0 && request.maxNodes>0;
}
}

extern "C" __declspec(dllexport) DWORD WINAPI Ai00ReadHierarchy(void *argument) {
    if(!readRequest(reinterpret_cast<const wchar_t *>(argument))) return 2;
    HWND window=nullptr; EnumWindows(findWindow,reinterpret_cast<LPARAM>(&window));
    if(!window) { writeResponse("{\"status\":\"ui_window_unavailable\"}"); return 3; }
    DWORD pid=0; DWORD tid=GetWindowThreadProcessId(window,&pid);
    if(pid!=GetCurrentProcessId()) { writeResponse("{\"status\":\"ui_window_mismatch\"}"); return 4; }
    completed=false; writeSucceeded=false; messageHook=SetWindowsHookExW(WH_GETMESSAGE,onMessage,selfModule,tid);
    if(!messageHook) { writeResponse("{\"status\":\"ui_hook_failed\"}"); return 5; }
    PostMessageW(window,WM_NULL,0,0);
    for(int i=0;i<200 && !completed;++i) Sleep(25);
    UnhookWindowsHookEx(messageHook); messageHook=nullptr;
    if(!completed) { writeResponse("{\"status\":\"ui_thread_timeout\"}"); return 6; }
    if(!writeSucceeded) return 7;
    return 0;
}

BOOL APIENTRY DllMain(HMODULE module,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH) { selfModule=module; DisableThreadLibraryCalls(module); }
    return TRUE;
}
