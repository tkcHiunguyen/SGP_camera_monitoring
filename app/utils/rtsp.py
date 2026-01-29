from urllib.parse import quote

from app.config.models import CameraConfig


def build_rtsp_url(config: CameraConfig) -> str:
    if config.rtsp_url:
        return config.rtsp_url
    user = quote(config.user, safe="")
    password = quote(config.password, safe="")
    auth = f"{user}:{password}@" if user or password else ""
    return f"rtsp://{auth}{config.ip}:{config.port}{config.stream_path}"
