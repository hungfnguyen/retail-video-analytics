from fastapi import APIRouter, HTTPException

from rva_api.mocks.live_mock import LIVE_DASHBOARD_MOCK
from rva_api.schemas.live import LiveDashboardData

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/{camera_id}/dashboard", response_model=LiveDashboardData)
def get_live_dashboard(camera_id: str) -> LiveDashboardData:
    camera_ids = {camera.camera_id for camera in LIVE_DASHBOARD_MOCK.cameras}

    if camera_id not in camera_ids:
        raise HTTPException(status_code=404, detail="Camera not found")

    data = LIVE_DASHBOARD_MOCK.model_copy(deep=True)
    data.selected_camera_id = camera_id
    data.frame.camera_id = camera_id
    data.stats.camera_id = camera_id

    return data
