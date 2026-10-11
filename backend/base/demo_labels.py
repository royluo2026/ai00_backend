"""Private test-demo display aliases; identifiers and selectors are not rewritten."""
import json,os,re
from functools import lru_cache
from pathlib import Path
from .demo_access import has_relation_demo_access

@lru_cache(maxsize=4)
def _aliases(filename,mtime_ns):
    value=json.loads(Path(filename).read_text(encoding='utf-8'))
    if value.get('schema')!='ai00.demo.display-aliases.v1':raise ValueError('demo_display_aliases_invalid')
    aliases=value.get('aliases')
    if not isinstance(aliases,dict) or any(not isinstance(k,str) or not k or not isinstance(v,str) or not v for k,v in aliases.items()):
        raise ValueError('demo_display_aliases_invalid')
    keys=sorted(aliases,key=len,reverse=True)
    return (re.compile('|'.join(re.escape(key) for key in keys)) if keys else None),aliases

def demo_display_mapper(user_gid:str):
    if not has_relation_demo_access(user_gid):return None
    filename=os.environ.get('AI00_DEMO_DISPLAY_ALIASES_FILE','').strip()
    if not filename:raise ValueError('demo_display_aliases_required')
    path=Path(filename)
    pattern,aliases=_aliases(str(path),path.stat().st_mtime_ns)
    return lambda value:pattern.sub(lambda match:aliases[match.group()],value) if pattern else value

def anonymize_demo_display(value:str,user_gid:str)->str:
    mapper=demo_display_mapper(user_gid)
    return mapper(value) if mapper else value
