# Camera Recorder (SGP)

Ứng dụng ghi hình camera (RTSP/Device) có Live View, Recorder, Edit video và cài đặt hệ thống.

## Tính năng chính
- Quản lý camera (RTSP hoặc Device)
- Live View đa màn hình + layout presets
- Recorder job + motion detection
- Edit video (trim/crop) + xuất file
- Settings chỉnh các tham số, lưu vào config

## Yêu cầu
- Windows 10/11 64-bit
- Python 3.10+ (khi chạy từ source)

## Chạy từ source
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Build EXE (onedir, bỏ PyTorch)
```powershell
python -m PyInstaller "D:\tracking camera SGP\main.py" --name CameraRecorder --noconsole --onedir --distpath "D:\tracking camera SGP\dist" --workpath "D:\tracking camera SGP\build" --specpath "D:\tracking camera SGP" --add-data "D:\tracking camera SGP\assets;assets" --add-data "D:\tracking camera SGP\config;config" --add-data "D:\tracking camera SGP\models;models" --exclude-module torch --exclude-module torchvision --exclude-module torchaudio --icon "D:\tracking camera SGP\assets\logo\logo_cam.ico"
```

Kết quả:
```
D:\tracking camera SGP\dist\CameraRecorder\CameraRecorder.exe
```

## Cấu hình
Config lưu ở:
```
config/config.json
config/cameras.json
```

Các tham số chính trong `config.json`:
- `files_dir`: thư mục lưu dữ liệu (Files/Media/Tracking/Exports)
- `fps_record`, `fps_detect`
- `days_keep`, `min_free_gb`
- `cam_reconnect_min_s`, `cam_reconnect_max_s`, `cam_stale_s`
- `yolo`, `tracking`

Bạn có thể chỉnh trực tiếp trong app tại tab **Settings**.

## Thư mục lưu trữ dữ liệu
Mặc định (theo `files_dir`):
```
Files/
  Media/
    Videos/YYYY/MM/DD/<CameraName>/
      Capture/         # ảnh khi motion active
  Tracking/
    YYYY/MM/DD/<CameraName>/   # clip motion (.ts / .mp4)
  Exports/             # video đã edit
```

## Ghi chú khi copy sang máy khác
- Nếu dùng bản **onedir**, hãy copy toàn bộ thư mục:
  ```
  dist/CameraRecorder/
  ```
- Có thể copy thêm `config/`, `models/`, `Files/` nếu muốn giữ cấu hình, model và dữ liệu.
- Nếu đổi máy, nhớ chỉnh `files_dir` trong Settings.

## Troubleshooting
- Không thấy icon app: build lại với `--icon` và file `logo_cam.ico`.
- EXE quá nặng: dùng bản onedir và loại bỏ PyTorch nếu chưa cần tracking.

