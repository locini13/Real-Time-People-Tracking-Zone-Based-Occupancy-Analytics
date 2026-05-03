"""
analytics.py — Per-Zone Occupancy Analytics Engine

Computes the following metrics per zone:
  - Live occupancy count (per frame)
  - Total unique visitors (deduplicated — re-entry is NOT double-counted)
  - Average dwell time in seconds
  - Peak occupancy and the timestamp it occurred

New Analytics Features:
  - Trajectory tracking (history of centroids)
  - Speed estimation (pixels/sec)
  - Zone Transitions (e.g. A->B)
  - Entry/Exit counting per zone
  - Loitering Detection
  - Overcrowding Alerts
"""

from collections import defaultdict
import math
from zones import ZONES

class ZoneAnalytics:
    """Accumulates per-zone analytics across all video frames."""

    def __init__(self, zone_keys: list, fps: float, overcrowding_threshold: int = 15, loitering_threshold_sec: int = 5):
        """
        Args:
            zone_keys: List of zone identifiers (e.g., ["A", "B", "C", "D"]).
            fps: Video frame rate, used to convert frame counts to seconds.
        """
        self.zone_keys = zone_keys
        self.fps = fps
        self.overcrowding_threshold = overcrowding_threshold
        self.loitering_threshold_frames = loitering_threshold_sec * fps

        # --- Per-zone data structures ---
        self.unique_visitors = {key: set() for key in zone_keys}
        self.dwell_frames = {key: defaultdict(int) for key in zone_keys}
        self.peak_occupancy = {key: (0, 0) for key in zone_keys}

        # --- New Analytics Features ---
        self.track_history = defaultdict(list) # track_id -> [(cx, cy), ...]
        self.zone_history = defaultdict(list)  # track_id -> [(zone_key, frame_number), ...]
        self.zone_transitions = defaultdict(int) # "A->B" -> count
        self.entry_exit_counts = {key: {"entries": 0, "exits": 0} for key in zone_keys}
        self.loitering_alerts = set() # set of track_ids currently loitering
        self.overcrowding_alerts = set() # set of zone_keys currently overcrowded
        self.speeds = {} # track_id -> speed estimate (pixels/sec)

        self.frame_log = []

    def update(self, frame_number: int, tracked_objects: list, zone_assignments: dict):
        """Update analytics with data from a single frame."""
        timestamp = frame_number / self.fps
        zone_counts = {key: 0 for key in self.zone_keys}
        current_frame_tracks = set()
        intrusion_alerts = []

        for obj in tracked_objects:
            track_id = obj['track_id']
            zone_key = zone_assignments.get(track_id)
            centroid = obj['centroid']
            current_frame_tracks.add(track_id)

            # 1. Trajectory Tracking
            self.track_history[track_id].append(centroid)
            # Keep history to a reasonable length (e.g. 150 frames = 6 seconds) for drawing
            if len(self.track_history[track_id]) > 150:
                self.track_history[track_id].pop(0)

            # 2. Speed Estimation
            history_len = len(self.track_history[track_id])
            if history_len > 10:
                past_centroid = self.track_history[track_id][-10]
                dist = math.hypot(centroid[0] - past_centroid[0], centroid[1] - past_centroid[1])
                # dist is pixels moved over 10 frames.
                speed_px_s = (dist / 10.0) * self.fps
                self.speeds[track_id] = speed_px_s
            else:
                self.speeds[track_id] = 0.0

            if zone_key is None:
                continue

            zone_counts[zone_key] += 1
            self.unique_visitors[zone_key].add(track_id)
            self.dwell_frames[zone_key][track_id] += 1

            # Intrusion Detection
            if ZONES.get(zone_key, {}).get("is_restricted", False):
                zone_name = ZONES[zone_key]["name"]
                intrusion_alerts.append([track_id, zone_key, zone_name])

            # 3. Loitering Detection
            if self.dwell_frames[zone_key][track_id] > self.loitering_threshold_frames:
                self.loitering_alerts.add(track_id)

            # 4. Zone Transitions & Entry/Exit Tracking
            if track_id not in self.zone_history:
                # First appearance
                self.zone_history[track_id].append((zone_key, frame_number))
                self.entry_exit_counts[zone_key]["entries"] += 1
            else:
                prev_zone, _ = self.zone_history[track_id][-1]
                if prev_zone != zone_key:
                    # Transition occurred
                    self.zone_transitions[f"{prev_zone}->{zone_key}"] += 1
                    self.entry_exit_counts[prev_zone]["exits"] += 1
                    self.entry_exit_counts[zone_key]["entries"] += 1
                    self.zone_history[track_id].append((zone_key, frame_number))
                    # Reset dwell time on zone change
                    self.dwell_frames[zone_key][track_id] = 0

        # Clean up loitering alerts if person left zone or frame
        to_remove = []
        for tid in self.loitering_alerts:
            if tid not in current_frame_tracks:
                to_remove.append(tid)
            else:
                current_zone = zone_assignments.get(tid)
                if current_zone and self.dwell_frames[current_zone][tid] <= self.loitering_threshold_frames:
                    to_remove.append(tid)
        for tid in to_remove:
            self.loitering_alerts.remove(tid)

        # 5. Overcrowding Alerts
        self.overcrowding_alerts.clear()
        for key in self.zone_keys:
            count = zone_counts[key]
            if count > self.peak_occupancy[key][0]:
                self.peak_occupancy[key] = (count, frame_number)
            if count > self.overcrowding_threshold:
                self.overcrowding_alerts.add(key)

        # Record frame log entry
        log_entry = {
            "frame": frame_number,
            "timestamp_sec": round(timestamp, 3),
            "alerts": {
                "loitering": list(self.loitering_alerts),
                "overcrowding": list(self.overcrowding_alerts),
                "intrusion": intrusion_alerts
            }
        }
        total = 0
        for key in self.zone_keys:
            log_entry[f"zone_{key}_count"] = zone_counts[key]
            total += zone_counts[key]
        log_entry["total_count"] = total

        self.frame_log.append(log_entry)

        return zone_counts

    def get_summary(self) -> dict:
        """Compute and return the final per-zone analytics summary."""
        summary = {}

        for key in self.zone_keys:
            unique_count = len(self.unique_visitors[key])
            if unique_count > 0:
                total_dwell_frames = sum(self.dwell_frames[key].values())
                avg_dwell_sec = (total_dwell_frames / unique_count) / self.fps
            else:
                avg_dwell_sec = 0.0

            peak_count, peak_frame = self.peak_occupancy[key]
            peak_timestamp = peak_frame / self.fps

            summary[key] = {
                "total_unique_visitors": unique_count,
                "average_dwell_time_sec": round(avg_dwell_sec, 2),
                "peak_occupancy": peak_count,
                "peak_occupancy_timestamp_sec": round(peak_timestamp, 2),
                "entries": self.entry_exit_counts[key]["entries"],
                "exits": self.entry_exit_counts[key]["exits"],
            }

        return summary

    def get_transitions(self) -> dict:
        return dict(self.zone_transitions)

    def get_frame_log(self) -> list:
        return self.frame_log

    def get_csv_header(self) -> str:
        cols = ["frame", "timestamp_sec"]
        for key in self.zone_keys:
            cols.append(f"zone_{key}_count")
        cols.append("total_count")
        return ",".join(cols)

    def get_csv_rows(self) -> list:
        rows = []
        for entry in self.frame_log:
            vals = [str(entry["frame"]), str(entry["timestamp_sec"])]
            for key in self.zone_keys:
                vals.append(str(entry[f"zone_{key}_count"]))
            vals.append(str(entry["total_count"]))
            rows.append(",".join(vals))
        return rows
