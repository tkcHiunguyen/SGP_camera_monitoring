from dataclasses import dataclass, field
from typing import List


@dataclass
class YoloConfig:
    model_path: str = "models/yolo.onnx"
    conf_thres: float = 0.5
    start_frames: int = 3
    stop_seconds: int = 5


@dataclass
class TrackingConfig:
    enabled: bool = True
    model_path: str = "models/yolo26n.pt"
    conf_thres: float = 0.6
    use_gpu: bool = True


@dataclass
class AppConfig:
    fps_record: int = 15
    fps_detect: int = 5
    days_keep: int = 7
    min_free_gb: int = 10
    yolo: YoloConfig = field(default_factory=YoloConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)


@dataclass
class CameraConfig:
    name: str
    ip: str
    port: int
    user: str
    password: str
    stream_path: str
    mode: str = "Continuous"
    source: str = "rtsp"
    rtsp_url: str = ""
    device_index: int = 0
    enabled: bool = True


@dataclass
class CameraRuntimeState:
    status: str = "Offline"
    last_error: str = ""
    last_frame_ts: float = 0.0
    mode: str = "Continuous"
    enabled: bool = True


@dataclass
class AppState:
    app: AppConfig = field(default_factory=AppConfig)
    cameras: List[CameraConfig] = field(default_factory=list)
