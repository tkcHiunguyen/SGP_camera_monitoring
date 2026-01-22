import cv2
import time

RTSP_TEMPLATE = (
    "rtsp://admin:bvTTDCaps999@hcv08bwvjn5.sn.mynetname.net:555/"
    "Streaming/Channels/{channel}"
)

START_INDEX = 1  # → 101
END_INDEX = 99  # → 9901
TIMEOUT_SEC = 3


def check_rtsp(url):
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    start = time.time()

    while time.time() - start < TIMEOUT_SEC:
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                cap.release()
                return True
        time.sleep(0.2)

    cap.release()
    return False


if __name__ == "__main__":
    for i in range(START_INDEX, END_INDEX + 1):
        channel = i * 100 + 1  # 101, 201, 301, ...
        rtsp_url = RTSP_TEMPLATE.format(channel=channel)

        ok = check_rtsp(rtsp_url)
        status = "✅ OK" if ok else "❌ FAIL"
        print(f"{status} | {rtsp_url}")
