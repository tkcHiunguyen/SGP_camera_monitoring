# Architecture

## Overview
This app is a Windows desktop recorder for multiple RTSP cameras with optional person-triggered recording. The system is split into UI, camera ingest, detection, recording, and storage utilities.

## Modules
- app/main.py: entrypoint, single-instance guard, logging, config bootstrap, UI startup.
- app/ui/: Tkinter UI for camera CRUD and settings.
- app/core/: camera manager, worker threads, view compositor, recording, and tracking.
- app/storage/: storage layout helpers and maintenance (retention, disk quota).
- app/utils/: shared helpers (paths, logging, RTSP URL builder).
- app/ui/widgets/: reusable Tkinter widgets.
- app/config/: config models and JSON load/save.
- app/utils/: shared helpers (logging, threading, time, paths).

## Data Flow
1. UI triggers config changes -> persisted to Files/config.json.
2. Camera workers read RTSP streams and update latest frames + online status.
3. View composer assembles 6-slot layout and sends to fullscreen window.
4. Recording loop writes per-camera files with hourly rotation.
5. Retention and disk quota tasks manage storage.
