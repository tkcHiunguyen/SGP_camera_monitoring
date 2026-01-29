import json
from dataclasses import asdict
from typing import List, Tuple

from app.config.models import AppConfig, CameraConfig, TrackingConfig, YoloConfig
from app.utils.paths import get_config_dir, get_files_dir


class ConfigStore:
    VERSION = 1

    def __init__(self) -> None:
        config_dir = get_config_dir()
        self.app_config_path = config_dir / "config.json"
        self.cameras_path = config_dir / "cameras.json"

    def ensure_dirs(self) -> None:
        get_files_dir().mkdir(parents=True, exist_ok=True)
        get_config_dir().mkdir(parents=True, exist_ok=True)

    def load(self) -> Tuple[AppConfig, List[CameraConfig]]:
        self.ensure_dirs()
        if not self.app_config_path.exists() and not self.cameras_path.exists():
            app_config = AppConfig()
            self.save(app_config, [])
            return app_config, []

        app_config = self._load_app_config()
        cameras = self._load_cameras()
        return app_config, cameras

    def save(self, app_config: AppConfig, cameras: List[CameraConfig]) -> None:
        self.ensure_dirs()
        app_payload = {
            "version": self.VERSION,
            "app": asdict(app_config),
        }
        self.app_config_path.write_text(
            json.dumps(app_payload, indent=2), encoding="utf-8"
        )
        self.cameras_path.write_text(
            json.dumps({"version": self.VERSION, "cameras": [asdict(c) for c in cameras]}, indent=2),
            encoding="utf-8",
        )

    def _parse_app_config(self, data: dict) -> AppConfig:
        app_data = data.get("app", {})
        yolo_data = app_data.get("yolo", {})
        tracking_data = app_data.get("tracking", {})
        return AppConfig(
            fps_record=app_data.get("fps_record", 15),
            fps_detect=app_data.get("fps_detect", 5),
            days_keep=app_data.get("days_keep", 7),
            min_free_gb=app_data.get("min_free_gb", 10),
            enable_disk_check=app_data.get("enable_disk_check", True),
            enable_disk_quota=app_data.get("enable_disk_quota", True),
            enable_retention=app_data.get("enable_retention", True),
            files_dir=app_data.get("files_dir", "Files"),
            cam_reconnect_min_s=app_data.get("cam_reconnect_min_s", 0.5),
            cam_reconnect_max_s=app_data.get("cam_reconnect_max_s", 30.0),
            cam_stale_s=app_data.get("cam_stale_s", 5.0),
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

    def _parse_camera(self, cam: dict) -> CameraConfig:
        source = cam.get("source", "rtsp")
        if source == "webcam":
            source = "device"
        return CameraConfig(
            name=cam.get("name", ""),
            ip=cam.get("ip", ""),
            port=int(cam.get("port", 554)),
            user=cam.get("user", ""),
            password=cam.get("password", ""),
            stream_path=cam.get("stream_path", "/profile2/media.smp"),
            mode=cam.get("mode", "Continuous"),
            source=source,
            rtsp_url=cam.get("rtsp_url", ""),
            device_index=int(cam.get("device_index", 0)),
            enabled=bool(cam.get("enabled", True)),
        )

    def _load_app_config(self) -> AppConfig:
        # Backward-compat: if old combined file exists, split it.
        legacy_path = self.app_config_path
        if legacy_path.exists():
            try:
                data = json.loads(legacy_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
            if "cameras" in data and not self.cameras_path.exists():
                app_config = self._parse_app_config(data)
                cameras = [self._parse_camera(cam) for cam in data.get("cameras", [])]
                self.save(app_config, cameras)
                return app_config
        if not self.app_config_path.exists():
            app_config = AppConfig()
            self.save(app_config, self._load_cameras())
            return app_config
        try:
            data = json.loads(self.app_config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            app_config = AppConfig()
            self.save(app_config, self._load_cameras())
            return app_config
        return self._parse_app_config(data)

    def _load_cameras(self) -> List[CameraConfig]:
        if not self.cameras_path.exists():
            return []
        try:
            data = json.loads(self.cameras_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return [self._parse_camera(cam) for cam in data.get("cameras", [])]
