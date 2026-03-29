import cv2
import os

# Add all cameras here
videos = {
    "cam4": "videos/cam4/video.mp4",
    "cam5": "videos/cam5/Indoor.mp4",
    "cam6": "videos/cam6/MallVideo.mp4",
    "cam7": "videos/cam7/playground.mp4"
}

for cam, video_path in videos.items():
    output_folder = f"videos/{cam}"
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
    print(f"{cam} → Total frames extracted: {count}")