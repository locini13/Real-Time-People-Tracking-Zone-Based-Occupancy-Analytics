import cv2
import numpy as np

width, height = 640, 480
fps = 25.0

fourcc = cv2.VideoWriter_fourcc(*'avc1')
out_writer = cv2.VideoWriter('test_avc1.mp4', fourcc, fps, (width, height))

for i in range(50):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.putText(frame, f"Frame {i}", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    out_writer.write(frame)

out_writer.release()
print("avc1 test done")
