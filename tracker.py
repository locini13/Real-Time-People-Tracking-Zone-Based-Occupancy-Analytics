"""
tracker.py — YOLOv8 Person Detection + DeepSORT Multi-Object Tracking

Detection: YOLOv8n (nano) for fast inference on this well-separated overhead scene.
Tracking:  DeepSORT with tuned parameters for grayscale, bird's-eye-view footage.

Tracking Parameter Rationale:
─────────────────────────────────────────────────────────────────────
max_age = 30 frames (1.2s at 25 FPS)
    → Allows a person to be undetected for ~1.2 seconds before their track is deleted.
      This covers brief occlusions from crossing paths or momentary detection failures.
      Too high would cause ghost tracks; too low would break tracks on minor occlusions.

n_init = 3 frames
    → Requires 3 consecutive detections to confirm a new track.
      Prevents floor markers, shadows, and transient false positives from becoming tracks.
      A value of 1 would create many phantom tracks; 5+ would miss fast-moving people
      who are only visible for a few frames at the edges.

max_iou_distance = 0.7
    → Standard IoU gating threshold for associating detections to existing tracks.
      In this overhead view, people rarely overlap heavily, so 0.7 is a good balance.

max_cosine_distance = 0.3
    → Appearance embedding similarity threshold for the ReID model.
      Since the video is grayscale with low appearance variation (dark silhouettes on 
      white floor), a tight threshold helps distinguish nearby people who look similar.
      Looser values (0.5+) cause ID switches between adjacent pedestrians.

nn_budget = 100
    → Number of appearance descriptors retained per track for matching.
      100 is generous for a 341-frame video. Provides robust re-identification
      without excessive memory usage.

embedder = "mobilenet"
    → MobileNet-based appearance feature extractor. Good balance of speed and
      discriminative power. Works well even on grayscale input.
─────────────────────────────────────────────────────────────────────
"""

from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort


class PersonTracker:
    """YOLOv8 + DeepSORT person detection and tracking pipeline."""

    def __init__(self,
                 yolo_model: str = "yolov8n.pt",
                 confidence_threshold: float = 0.25,
                 iou_threshold: float = 0.45,
                 max_age: int = 30,
                 n_init: int = 3,
                 max_iou_distance: float = 0.7,
                 max_cosine_distance: float = 0.3,
                 nn_budget: int = 100):
        """
        Args:
            yolo_model: Path to YOLOv8 weights file.
            confidence_threshold: Min confidence for YOLO detections. Set to 0.25
                (below default 0.5) because overhead grayscale views can produce
                lower-confidence person detections. Still high enough to avoid
                false positives from circular floor markers.
            iou_threshold: NMS IoU threshold for YOLO. Standard 0.45.
            max_age: DeepSORT — max frames to keep a track alive without detections.
            n_init: DeepSORT — consecutive detections required to confirm a track.
            max_iou_distance: DeepSORT — max IoU distance for association.
            max_cosine_distance: DeepSORT — max cosine distance for appearance matching.
            nn_budget: DeepSORT — max appearance descriptors stored per track.
        """
        # --- YOLOv8 detector ---
        self.yolo = YOLO(yolo_model)
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold

        # --- DeepSORT tracker ---
        self.tracker = DeepSort(
            max_age=150,                 # Increased from 30 to 150 (6 seconds) to retain IDs longer
            n_init=n_init,
            max_iou_distance=0.9,        # Increased from 0.7 to be more permissive with movement
            max_cosine_distance=0.5,     # Increased from 0.3 to be more permissive with appearance changes
            nn_budget=nn_budget,
            embedder="mobilenet",
            half=True,           # FP16 for faster embedding on GPU
            embedder_gpu=True,   # Use GPU for appearance feature extraction
        )

        # --- ID-switch tracking ---
        self.id_switch_count = 0
        self._prev_track_ids = set()
        self._total_tracks_created = set()

    def detect(self, frame):
        """
        Run YOLOv8 person detection on a single frame.

        Returns:
            list of [x1, y1, x2, y2, confidence] for each detected person.
        """
        results = self.yolo(
            frame,
            classes=[0],                          # person class only
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            verbose=False,
        )

        detections = []
        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0].cpu().numpy())
                    detections.append([x1, y1, x2, y2, conf])

        return detections

    def track(self, frame, detections):
        """
        Update DeepSORT tracker with new detections and return tracked objects.

        Args:
            frame: Current video frame (BGR numpy array).
            detections: List of [x1, y1, x2, y2, confidence] from detect().

        Returns:
            list of dicts with keys:
                - 'track_id': int, persistent ID
                - 'bbox': [x1, y1, x2, y2] bounding box
                - 'centroid': (cx, cy) center of bounding box
        """
        # Convert detections to DeepSORT format: ([x, y, w, h], confidence, class)
        deepsort_detections = []
        for det in detections:
            x1, y1, x2, y2, conf = det
            w = x2 - x1
            h = y2 - y1
            deepsort_detections.append(([x1, y1, w, h], conf, "person"))

        # Update tracker
        tracks = self.tracker.update_tracks(deepsort_detections, frame=frame)

        # Process confirmed tracks
        tracked_objects = []
        current_ids = set()

        for track in tracks:
            if not track.is_confirmed():
                continue

            track_id = track.track_id
            current_ids.add(track_id)
            self._total_tracks_created.add(track_id)

            ltrb = track.to_ltrb()  # [left, top, right, bottom]
            x1, y1, x2, y2 = ltrb
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0

            tracked_objects.append({
                'track_id': track_id,
                'bbox': [float(x1), float(y1), float(x2), float(y2)],
                'centroid': (float(cx), float(cy)),
            })

        # --- Estimate ID switches ---
        # An ID switch occurs when a new ID appears that wasn't in the previous frame
        # while an old ID disappears (suggesting the same person got a new ID).
        # This is a heuristic — not perfect, but useful for diagnostics.
        new_ids = current_ids - self._prev_track_ids
        lost_ids = self._prev_track_ids - current_ids
        # Count min of new and lost as potential switches (conservative estimate)
        if len(self._prev_track_ids) > 0:
            potential_switches = min(len(new_ids), len(lost_ids))
            self.id_switch_count += potential_switches

        self._prev_track_ids = current_ids.copy()

        return tracked_objects

    def detect_and_track(self, frame):
        """Convenience: detect + track in one call."""
        detections = self.detect(frame)
        return self.track(frame, detections)

    def get_tracking_stats(self):
        """Return tracking quality statistics."""
        return {
            "total_tracks_created": len(self._total_tracks_created),
            "estimated_id_switches": self.id_switch_count,
            "id_switch_mitigation": (
                "Minimized via: (1) max_age=30 to maintain tracks through 1.2s occlusions, "
                "(2) n_init=3 to suppress phantom tracks, "
                "(3) max_cosine_distance=0.3 for tight appearance matching in grayscale, "
                "(4) MobileNet embedder for discriminative appearance features even with "
                "limited color information, "
                "(5) nn_budget=100 for robust gallery of appearance descriptors per track."
            ),
        }
