"""Same-origin runtime endpoints for Browser's fixed /api proxy."""
from fastapi import APIRouter

from backend.routers.admin import active_data_environment, data_environments, switch_data_environment, test_data_environment_connection

router = APIRouter(prefix='/api/runtime', tags=['runtime'])
router.add_api_route('/data-environment', active_data_environment, methods=['GET'])
router.add_api_route('/data-environments', data_environments, methods=['GET'])
router.add_api_route('/data-environments/switch', switch_data_environment, methods=['POST'])
router.add_api_route('/data-environments/connection-test', test_data_environment_connection, methods=['POST'])
