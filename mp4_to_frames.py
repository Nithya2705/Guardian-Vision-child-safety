import cv2
import os

video_path = "myvideo.mp4"     # Your MP4 file
output_folder = "videos/cam4" # Or cam1 / cam2 / cam3

os.makedirs(output_folder, exist_ok=True)

cap = cv2.VideoCapture(video_path)
count = 1

while True:
    success, frame = cap.read()
    if not success:
        break

    filename = f"{count:06d}.jpg"
    cv2.imwrite(os.path.join(output_folder, filename), frame)
    count += 1

cap.release()
print("Total frames extracted:", count)
