from unittest.mock import patch, Mock

from plugins.knowledge.knowledge_backend import feishu_metadata as module


def test_metadata_uses_creator_date_and_user_scoped_cache():
    module._cache.clear()
    rows = [{'gid': 'r1', 'active': True, 'document_url': 'https://li.feishu.cn/docx/document123'},
            {'gid': 'r2', 'active': True, 'error_code':'document_link_duplicate', 'document_url': 'https://li.feishu.cn/docx/document123'}]
    with patch.object(module.feishu_service, 'resolve_wiki_node', return_value={
        'creator': 'ou_creator', 'owner': 'ou_owner', 'obj_edit_time': '1700000000',
    }) as node, patch.object(module.feishu_service, 'get_user_names_as_user', return_value={'ou_creator':'作者甲'}) as names:
        result = module.read_source_metadata(rows, user_gid='u1', access_token='delegated')
        assert result['r1']['feishu_author_name'] == '作者甲'
        assert result['r2'] == result['r1']
        assert result['r1']['feishu_modified_at'] == '2023-11-14T22:13:20+00:00'
        node.assert_called_once_with('document123', access_token='delegated', obj_type='docx')
        names.assert_called_once_with(['ou_creator'], access_token='delegated')
        module.read_source_metadata(rows, user_gid='u1', access_token='delegated')
        assert node.call_count == 1
        module.read_source_metadata(rows, user_gid='u2', access_token='other-user')
        assert node.call_count == 2
    module._cache.clear()


def test_denied_metadata_does_not_fail_other_documents_or_invent_author():
    from requests import HTTPError, Response
    module._cache.clear()
    response = Response(); response.status_code = 400; response._content = b'{"code":131006}'
    def resolve(token, **kwargs):
        if token == 'denied123':
            raise HTTPError(response=response)
        return {'creator':'ou_creator', 'obj_edit_time':'1700000000'}
    rows = [{'gid': token, 'active':True,'document_url':f'https://li.feishu.cn/wiki/{token}'} for token in ('denied123','allowed123')]
    with patch.object(module.feishu_service, 'resolve_wiki_node', side_effect=resolve), \
         patch.object(module.feishu_service, 'get_user_names_as_user', side_effect=ValueError('Contacts unavailable')):
        result = module.read_source_metadata(rows, user_gid='u',access_token='delegated')
    assert result['denied123']['feishu_metadata_status'] == 'view_denied'
    assert result['allowed123']['feishu_modified_at']
    assert result['allowed123']['feishu_author_name'] is None
    module._cache.clear()


def test_creator_name_service_is_delegated_read_only():
    from backend.services.feishu_service import FeishuService
    response = Mock(); response.json.return_value = {'code':0,'data':{'items':[{'open_id':'ou_creator','name':'作者甲'}]}}
    with patch('backend.services.feishu_service.requests.get',return_value=response) as get:
        assert FeishuService().get_user_names_as_user(['ou_creator'],access_token='delegated') == {'ou_creator':'作者甲'}
    assert get.call_args.args[0].endswith('/contact/v3/users/batch')
    assert get.call_args.kwargs['headers']['Authorization'] == 'Bearer delegated'
