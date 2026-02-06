Remove-Item .\build, .\dist -Recurse -Force; python -m PyInstaller .\CameraRecorder.spec --noconfirm
