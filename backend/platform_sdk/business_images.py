"""Read a stored business image through fixed configured storage transports."""
from pathlib import Path
from urllib.parse import urlsplit,unquote
from backend.core import storage,ois_storage

MAXIMUM=5*1024*1024
def image_type(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):return 'image/png'
    if data.startswith(b'\xff\xd8\xff'):return 'image/jpeg'
    if data.startswith((b'GIF87a',b'GIF89a')):return 'image/gif'
    if data[:4]==b'RIFF' and data[8:12]==b'WEBP':return 'image/webp'
    raise ValueError('unsupported_image_content')

def read_stored_image(record, *, static_root):
    """record must originate from the authorized owner's stored picture column."""
    url=str(record.get('url') or '');key=str(record.get('object_key') or '')
    if record.get('storage')=='ois' and key:
        data=ois_storage.get_immutable(key,maximum=MAXIMUM)
    elif urlsplit(url).path.startswith('/static/uploads/bop_pics/'):
        name=unquote(urlsplit(url).path.removeprefix('/static/uploads/bop_pics/'))
        root=Path(static_root).resolve();target=(root/name).resolve()
        if target.parent!=root or target.is_symlink():raise ValueError('invalid_stored_image_path')
        with target.open('rb') as stream:data=stream.read(MAXIMUM+1)
    else:
        # Only the two configured owner stores can resolve historical public URLs.
        minio=storage._get_minio_config();ois=ois_storage._get_ois_config()
        parsed=urlsplit(url);match=None
        for base,backend in ((minio.get('public_url'),'minio'),(ois.get('public_base_url'),'ois')):
            parsed_base=urlsplit(str(base or '').rstrip('/'));prefix=parsed_base.path.rstrip('/')+'/'
            if base and (parsed.scheme,parsed.netloc)==(parsed_base.scheme,parsed_base.netloc) and parsed.path.startswith(prefix):
                match=(backend,unquote(parsed.path[len(prefix):]));break
        if match is None:raise ValueError('unsupported_stored_image_location')
        backend,key=match
        data=(ois_storage.get_immutable if backend=='ois' else storage.get_immutable)(key,maximum=MAXIMUM)
    if not isinstance(data,bytes) or len(data)>MAXIMUM:raise ValueError('stored_image_unavailable')
    return data,image_type(data)
