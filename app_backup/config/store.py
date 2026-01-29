import json
from dataclasses import asdict
from typing import List, Tuple

from app.config.models import AppConfig, CameraConfig, TrackingConfig, YoloConfig
from app.utils.paths import get_config_dir, get_files_dir


class ConfigStore:
    def __init__(self) -> None:
        self.config_path = get_config_dir() / "config.json"

    def ensure_dirs(self) -> None:
        get_files_dir().mkdir(parents=True, exist_ok=True)
        get_config_dir().mkdir(parents=True, exist_ok=True)

    def load(self) -> Tuple[AppConfig, List[CameraConfig]]:
        self.ensure_dirs()
        if not self.config_path.exists():
            app_config = AppConfig()
            self.save(app_config, [])
            return app_config, []

        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            app_config = AppConfig()
            self.save(app_config, [])
            return app_config, []

        app_data = data.get("app", {})
        yolo_data = app_data.get("yolo", {})
        tracking_data = app_data.get("tracking", {})
        app_config = AppConfig(
            fps_record=app_data.get("fps_record", 15),
            fps_detect=app_data.get("fps_detect", 5),
            days_keep=app_data.get("days_keep", 7),
            min_free_gb=app_data.get("min_free_gb", 10),
            yolo=YoloConfig(
                model_path=yolo_data.get("model_path", "models/yolo.onnx"),
                conf_thres=yolo_data.get("conf_thres", 0.5),
                start_frames=yolo_data.get("start_frames", 3),
                stop_seconds=yolo_data.get("stop_seconds", 5),
            ),
            tracking=TrackingConfig(
                enabled=tracking_data.get("enabled", True),
                model_path=tracking_data.get("model_path", "models/yolo26n.pt"),
                conf_thres=tracking_data.get("conf_thres", 0.6),
                use_gpu=tracking_data.get("use_gpu", True),
            ),
        )

        cameras = []
        for cam in data.get("cameras", []):
            cameras.append(
                CameraConfig(
                    name=cam.get("name", ""),
                    ip=cam.get("ip", ""),
                    port=int(cam.get("port", 554)),
                    user=cam.get("user", ""),
                    password=cam.get("password", ""),
                    stream_path=cam.get("stream_path", "/profile2/media.smp"),
                    mode=cam.get("mode", "Continuous"),
                    source="device" if cam.get("source") == "webcam" else cam.get("source", "rtsp"),
                    rtsp_url=cam.get("rtsp_url", ""),
                    device_index=int(cam.get("device_index", 0)),
                    enabled=bool(cam.get("enabled", True)),
                )
            )
        return app_config, cameras

    def save(self, app_config: AppConfig, cameras: List[CameraConfig]) -> None:
        self.ensure_dirs()
        payload = {
            "app": asdict(app_config),
            "cameras": [asdict(c) for c in cameras],
        }
        self.config_path.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
