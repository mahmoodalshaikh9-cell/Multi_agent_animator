from pathlib import Path
import cv2


def extract_frames(video: Path, output_dir: Path, count=5):
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    paths = []

    for i in range(count):
        frame_number = int(
            i * (total - 1) / max(count - 1, 1)
        )

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

        ok, frame = cap.read()

        if not ok:
            continue

        path = output_dir / f"frame_{i}.jpg"
        cv2.imwrite(str(path), frame)
        paths.append(path)

    cap.release()

    return paths