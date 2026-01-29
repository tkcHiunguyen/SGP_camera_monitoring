import json
import time
from pathlib import Path

import cv2

from app.utils.paths import get_config_dir

_DEFAULTS = {
    "history": 300,
    "var_threshold": 16,
    "detect_shadows": True,
    "min_area": 500,
    "min_width": 30,
    "min_height": 15,
    "erode_iter": 1,
    "dilate_iter": 2,
    "learning_rate": 0.01,
    "fg_threshold": 127,
    "mask_blur": 5,
    "persist_frames": 2,
}

_CONFIG_CACHE = {"data": None, "mtime": None, "last_check": 0.0}


def get_motion_config() -> dict:
    now = time.time()
    if _CONFIG_CACHE["data"] is not None and now - _CONFIG_CACHE["last_check"] < 0.5:
        return _CONFIG_CACHE["data"]
    _CONFIG_CACHE["last_check"] = now
    path = _get_config_path()
    mtime = path.stat().st_mtime if path.exists() else None
    if _CONFIG_CACHE["data"] is None or mtime != _CONFIG_CACHE["mtime"]:
        _CONFIG_CACHE["data"] = _load_config(path)
        _CONFIG_CACHE["mtime"] = mtime
    return _CONFIG_CACHE["data"]


def ensure_motion(state: dict, config: dict) -> None:
    key = (config["history"], config["var_threshold"], config["detect_shadows"])
    if state.get("bg") is None or state.get("cfg_key") != key:
        state["bg"] = cv2.createBackgroundSubtractorMOG2(
            history=config["history"],
            varThreshold=config["var_threshold"],
            detectShadows=config["detect_shadows"],
        )
        state["cfg_key"] = key
        state["persist"] = 0


def apply_motion(frame, state: dict, config: dict) -> tuple:
    bg = state.get("bg")
    if bg is None:
        return [], None
    fg = bg.apply(frame, learningRate=config["learning_rate"])
    _, fg = cv2.threshold(fg, config["fg_threshold"], 255, cv2.THRESH_BINARY)
    blur_size = int(config.get("mask_blur", 0) or 0)
    if blur_size > 0:
        if blur_size % 2 == 0:
            blur_size += 1
        fg = cv2.medianBlur(fg, blur_size)
    if config["erode_iter"] > 0:
        fg = cv2.erode(fg, None, iterations=config["erode_iter"])
    if config["dilate_iter"] > 0:
        fg = cv2.dilate(fg, None, iterations=config["dilate_iter"])
    contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        if cv2.contourArea(contour) < config["min_area"]:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if w < config["min_width"] or h < config["min_height"]:
            continue
        boxes.append((x, y, w, h))
    persist = max(1, int(config.get("persist_frames", 1) or 1))
    if persist > 1:
        if boxes:
            state["persist"] = int(state.get("persist", 0)) + 1
        else:
            state["persist"] = 0
        if state["persist"] < persist:
            return [], fg
    return boxes, fg


def _get_config_path() -> Path:
    return get_config_dir() / "motion_config.json"


def _load_config(path: Path) -> dict:
    config = dict(_DEFAULTS)
    if not path.exists():
        return config
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return config
    for key in config:
        if key in data:
            config[key] = data[key]
    return config
