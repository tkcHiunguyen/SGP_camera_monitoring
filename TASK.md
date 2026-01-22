# CODEX TASK SPEC - Rewrite Camera Recorder (RTSP Multi-Cam) with YOLO Person Trigger

## Role
You are an implementation agent. Rewrite the entire application from scratch (new repo layout, new code). Follow this spec exactly. Do not preserve old architecture or globals(). Keep the user-facing features, but redesign internals cleanly and maintainably.

## High-level goal
Build a Windows desktop app that:
- Manages multiple RTSP IP cameras (add/edit/delete).
- Shows a fullscreen OpenCV view composed of 6 slots (1 large + 5 small).
- Records videos per camera:
  - Mode A: Continuous (always record).
  - Mode B: Person (YOLO detects person -> record only when person present, with debounce).
- Keeps existing behaviors:
  - Hourly file rotation.
  - Retention delete old videos.
  - Disk free threshold disables writing (view still works).
  - Basic status indicators Online/Offline and Mode.
- Must support clean shutdown, robust reconnect, and stable operation with multiple cameras.

## Non-goals
- No AI training. Only inference.
- No web backend.
- No cloud upload.
- No database required (config file is enough).

---

# Milestones

## M0 - Repo scaffold + standards (deliverable: runnable skeleton) [DONE]
### Tasks
1. Create repo structure:
   - app/
     - main.py
     - ui/
     - core/
     - detect/
     - storage/
     - config/
     - utils/
   - assets/ (icon)
   - models/ (yolo weights or onnx)
   - docs/
   - tests/
2. Add requirements.txt.
3. Add logging (rotating file logs): Files/Log/app.log.
4. Implement single-instance for Windows using a mutex.
5. Implement config as JSON: Files/config.json.
6. Add docs/ARCHITECTURE.md describing modules and data flow.

### Acceptance criteria
- python app/main.py opens a minimal UI window and cleanly exits.
- Files/config.json created/loaded.
- Only 1 instance can run.

---

## M1 - Core camera ingest + UI CRUD (deliverable: multi-cam online/offline with view frames)
### Design constraints
- Do NOT use globals() for camera state.
- Use dataclasses:
  - CameraConfig
  - AppConfig
  - CameraRuntimeState
- Each camera runs in its own worker thread, with clean stop signaling.
- Use OpenCV VideoCapture with reconnect/backoff.

### Tasks
1. UI (Tkinter):
   - Treeview columns: No, Camera Name, IP, Status, Mode
   - Form fields: name, ip, port, user, password, stream_path (default: /profile2/media.smp)
   - Buttons: Add, Edit, Delete, Test Connection, Save Config
   - Settings panel: fps_record, fps_detect, days_keep, min_free_gb, yolo_conf, start_frames, stop_seconds
2. Implement CameraManager:
   - Add camera => start worker
   - Remove camera => stop worker, cleanup
   - Persist config to JSON on changes
3. Implement CameraWorker:
   - Build RTSP URL (handle URL encoding for user/pass)
   - Connect -> read frames -> update runtime status Online/Offline
   - Provide latest frame to view compositor (thread-safe)
   - Reconnect with exponential backoff on failure
4. Implement View foundation:
   - ViewComposer maintains a 1920x1080 canvas (numpy)
   - Slot layout:
     - viewmain: x[0:1280], y[0:720]   size 1280x720
     - view2:   x[0:640],  y[720:1080] size 640x360
     - view3:   x[640:1280],y[720:1080] size 640x360
     - view4:   x[1280:1920],y[0:360] size 640x360
     - view5:   x[1280:1920],y[360:720] size 640x360
     - view6:   x[1280:1920],y[720:1080] size 640x360
   - Clear slot uses a placeholder frame.
5. Implement ViewWindow:
   - OpenCV fullscreen window "view"
   - Right-click determines slot and opens popup menu of camera names to assign to that slot
   - ESC exits fullscreen (but app still runs)

### Acceptance criteria
- Add 2 cameras; app shows Online/Offline changes correctly.
- Fullscreen view shows assigned camera frames in slots.
- No crashes on camera disconnect; reconnect works.

---

## M2 - Recording engine + hourly rotation + retention + disk quota (deliverable: stable recorder Continuous)
### Tasks
1. Implement VideoWriterManager per camera:
   - Directory structure:
     - Files/Videos/<CameraName>/<Year>/<Month>/
   - File naming:
     - <CameraName> dd-mm-YYYY HHh.mp4
     - If name exists, append minutes/seconds.
   - Codec: mp4 compatible (prefer mp4v for maximum Windows compatibility; allow config override)
   - Rotate file on hour change reliably (timestamp-based, not toggled flags)
2. Implement Record loop:
   - Record at fps_record (skip frames accordingly)
3. Implement Disk quota checker:
   - Check free GB on the drive hosting Files/Videos
   - If free < min_free_gb: disable writing; view remains
4. Implement retention:
   - Delete videos older than days_keep (prefer parsing by file modified time or folder name)
   - Log deletions

### Acceptance criteria
- Continuous mode records mp4 per hour.
- Hourly rotation works.
- Retention deletes old content.
- Disk low disables writing but app continues.

---

## M3 - YOLO person detection mode (deliverable: Person mode triggers recording)
### Runtime choice
Preferred implementation: ONNXRuntime.
Fallback: Ultralytics (PyTorch).
Choose ONNXRuntime by default if feasible.

### Tasks
1. Implement PersonDetector singleton:
   - Load model once.
   - detect(frame_resized) -> has_person, boxes, scores
   - Filter class=person only.
   - Use config thresholds: yolo_conf (and iou if applicable).
2. Detection pipeline:
   - Detect at fps_detect (independent from record fps).
   - Resize frame for detection (e.g., width 640).
   - Optional semaphore to limit concurrent inference if many cameras.
3. Person-trigger logic (debounce):
   - start_frames: require N consecutive detections to start recording
   - stop_seconds: stop recording if no detection for T seconds
   - In Person mode: only write frames while "recording active"
4. Snapshot (optional but recommended):
   - When detection starts or periodic cooldown: save JPEG to:
     - Files/Videos/<Cam>/<Year>/<Month>/Pictures/<Cam> dd-mm-YYYY HHhMMmSSs.jpg
   - Optionally draw bounding boxes on snapshot
5. UI integration:
   - Mode column toggles between Continuous and Person
   - Settings editable and saved

### Acceptance criteria
- In Person mode, no person => no recording file growth (or file not created until triggered).
- Person appears => starts recording after N frames.
- Person disappears => stops after T seconds.
- Snapshot saved according to cooldown.

---

## M4 - Hardening + packaging (deliverable: Windows exe)
### Tasks
1. Clean shutdown:
   - Stop all workers, release writers, destroy OpenCV windows, exit UI.
2. Error handling:
   - No bare except: pass. Log exceptions with stack traces.
3. Packaging:
   - PyInstaller spec
   - Include assets icon and model files
   - Ensure config + Files folder created automatically
4. Documentation:
   - docs/USAGE.md: setup, add cam, modes, output folders, tuning
   - docs/TROUBLESHOOTING.md: RTSP, firewall, disk, performance

### Acceptance criteria
- exe runs on Windows without Python installed.
- Runs multiple cameras stably for extended period (basic soak test).
- No orphan processes after exit.

---

# Implementation notes (must follow)

## Threading and shared data
- Use threading.Event for stop signals.
- Use locks or thread-safe containers for latest frames and statuses.
- Avoid UI updates from worker threads; marshal to Tkinter main thread via after().

## URL encoding
- Username/password may include special characters. Encode them safely.

## Performance
- Separate record FPS from detect FPS.
- Avoid running YOLO inference on every captured frame.
- Avoid copying large frames unnecessarily.

## Logs
- Log: start/stop, online/offline, reconnect attempts, file rotation, disk low, retention deletions, detector load.

---

# Config schema (config.json)
Include at minimum:
- app:
  - fps_record: int
  - fps_detect: int
  - days_keep: int
  - min_free_gb: int
  - yolo:
    - model_path: string
    - conf_thres: float
    - start_frames: int
    - stop_seconds: int
- cameras: list of:
  - name, ip, port, user, password, stream_path, mode

---

# Deliverables checklist
- [ ] Source code in new structure
- [ ] config.json load/save and migrate (optional)
- [ ] UI CRUD + settings
- [ ] View fullscreen 6 slots with right-click assignment
- [ ] Continuous recording per-hour
- [ ] Retention + disk quota
- [ ] YOLO Person mode with debounce
- [ ] Logs and clean shutdown
- [ ] PyInstaller build artifacts + docs

END OF SPEC
