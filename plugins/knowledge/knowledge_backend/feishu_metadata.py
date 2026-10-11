"""Bounded, user-scoped read cache for Feishu document creator and modification date."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Lock
from time import monotonic
from urllib.parse import urlparse

from backend.platform_sdk.feishu import feishu_service
from .feishu_catalog import parse_document_url

_cache = OrderedDict()
_lock = Lock()


def read_source_metadata(rows, *, user_gid, access_token):
    results, pending, groups = {}, [], {}
    for row in rows:
        url = row.get('document_url')
        if not url or row.get('error_code') not in {None, 'document_link_duplicate'} or not row.get('active'):
            continue
        key = (user_gid, url)
        with _lock:
            cached = _cache.get(key)
            if cached and cached[0] > monotonic():
                _cache.move_to_end(key)
                results[row['gid']] = dict(cached[1])
                continue
        if url not in groups:
            pending.append(row)
        groups.setdefault(url, []).append(row)

    def read(row):
        try:
            url = row['document_url']
            token = parse_document_url(url)
            kind = urlparse(url).path.strip('/').split('/')[0]
            node = feishu_service.resolve_wiki_node(token, access_token=access_token,
                                                  **({'obj_type': kind} if kind != 'wiki' else {}))
            author = node.get('creator')
            timestamp = node.get('obj_edit_time')
            modified = datetime.fromtimestamp(int(timestamp), UTC).isoformat() if timestamp else None
            return row, {'feishu_author_name': None, 'feishu_modified_at': modified,
                         'feishu_metadata_status': 'ready'}, author
        except Exception as exc:
            code = None
            if getattr(exc, 'response', None) is not None:
                try:
                    code = exc.response.json().get('code')
                except ValueError:
                    pass
            denied = code in {131006, 1310213, 1770032}
            return row, {'feishu_author_name': None, 'feishu_modified_at': None,
                         'feishu_metadata_status': 'view_denied' if denied else 'unavailable'}, None

    with ThreadPoolExecutor(max_workers=4) as pool:
        fresh = list(pool.map(read, pending))
    authors = sorted({author for _, _, author in fresh if author})
    names = {}
    for offset in range(0, len(authors), 50):
        try:
            names.update(feishu_service.get_user_names_as_user(authors[offset:offset + 50], access_token=access_token))
        except Exception:
            pass  # Document metadata remains useful when Contacts hides a creator's name.
    for row, metadata, author in fresh:
        metadata['feishu_author_open_id'] = author
        metadata['feishu_author_name'] = names.get(author)
        for related in groups[row['document_url']]:
            results[related['gid']] = dict(metadata)
        with _lock:
            _cache[(user_gid, row['document_url'])] = (monotonic() + (300 if metadata['feishu_metadata_status'] == 'ready' else 30), dict(metadata))
            _cache.move_to_end((user_gid, row['document_url']))
            while len(_cache) > 1024:
                _cache.popitem(last=False)
    return results
