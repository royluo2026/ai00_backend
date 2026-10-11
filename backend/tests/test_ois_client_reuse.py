from types import SimpleNamespace
from unittest.mock import patch
from backend.core import ois_storage


def test_sdk_client_reuses_credentials_and_invalidates_on_configuration_change():
    ois_storage._client_from_options.cache_clear()
    config = {"identify": "bucket", "env": "test", "idaas_client_secret": "first"}
    with patch.object(ois_storage, '_get_ois_config', side_effect=lambda: dict(config)), \
         patch('client.ois_s3_client.ClientOptions', side_effect=lambda **kw: SimpleNamespace(**kw)), \
         patch('client.ois_s3_client.OisS3Client', side_effect=lambda options: SimpleNamespace(options=options)) as create:
        first, error = ois_storage._make_client()
        assert error is None
        assert ois_storage._make_client()[0] is first
        assert create.call_count == 1
        config['idaas_client_secret'] = 'rotated'
        assert ois_storage._make_client()[0] is not first
        assert create.call_count == 2
    ois_storage._client_from_options.cache_clear()


def test_failed_initialization_is_not_cached():
    ois_storage._client_from_options.cache_clear()
    client = object()
    with patch.object(ois_storage, '_get_ois_config', return_value={'identify': 'bucket'}), \
         patch('client.ois_s3_client.ClientOptions', side_effect=lambda **kw: SimpleNamespace(**kw)), \
         patch('client.ois_s3_client.OisS3Client', side_effect=[RuntimeError('temporary failure'), client]) as create:
        assert ois_storage._make_client()[0] is None
        assert ois_storage._make_client()[0] is client
        assert create.call_count == 2
    ois_storage._client_from_options.cache_clear()
