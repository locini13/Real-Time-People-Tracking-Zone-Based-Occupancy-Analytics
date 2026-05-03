"""
main.py — Pipeline Orchestrator for Real-Time People Tracking & Zone-Based Occupancy Analytics
"""

import os
import sys
import json
import time

import cv2
import numpy as np
import imageio

from tracker import PersonTracker
from zones import ZONES, ZONE_KEYS, get_zone, draw_zone_overlays, draw_tracked_person, set_custom_zones
from analytics import ZoneAnalytics

def create_hud(frame: np.ndarray, frame_number: int, fps: float,
               total_frames: int, total_tracked: int) -> np.ndarray:
    timestamp = frame_number / fps
    bar_height = 45
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (frame.shape[1], bar_height), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

    info_left = f"Frame: {frame_number}/{total_frames}  |  Time: {timestamp:.2f}s"
    cv2.putText(frame, info_left, (15, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

    info_right = f"People Tracked: {total_tracked}"
    (tw, _), _ = cv2.getTextSize(info_right, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
    cv2.putText(frame, info_right, (frame.shape[1] - tw - 15, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 200), 2, cv2.LINE_AA)
    return frame

def get_dominant_color(roi):
    """Simple heuristic to get dominant color of a bounding box ROI."""
    if roi.size == 0:
        return "Unknown"
    
    # Downsample for speed
    small_roi = cv2.resize(roi, (16, 16))
    pixels = np.float32(small_roi.reshape(-1, 3))
    
    n_colors = 1
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 0.1)
    flags = cv2.KMEANS_RANDOM_CENTERS
    _, labels, palette = cv2.kmeans(pixels, n_colors, None, criteria, 10, flags)
    
    dom_color = palette[0]
    # Simple color classification based on hue
    b, g, r = dom_color
    hsv = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV)[0][0]
    h, s, v = hsv
    
    if s < 40 and v > 200: return "White"
    if v < 50: return "Black"
    if s < 40: return "Grey"
    if h < 10 or h > 170: return "Red"
    if 10 <= h < 35: return "Orange/Brown"
    if 35 <= h < 85: return "Green"
    if 85 <= h < 130: return "Blue"
    if 130 <= h <= 170: return "Purple"
    return "Unknown"

def get_mock_demographics(track_id):
    """Mock demographic data for demonstration."""
    import random
    random.seed(track_id)
    age = random.choice(["18-25", "26-35", "36-45", "46+"])
    gender = random.choice(["M", "F"])
    return {"age": age, "gender": gender}

def run_pipeline(input_video: str = "vidp.mp4",
                 output_video: str = "output_annotated.mp4",
                 analysis_recording: str = "analysis_recording.avi",
                 output_json: str = "analytics_summary.json",
                 output_csv: str = "occupancy_log.csv",
                 heatmap_output: str = "heatmap.jpg",
                 custom_zones_data: list = None):
    print("=" * 70)
    print("  Real-Time People Tracking & Zone-Based Occupancy Analytics")
    print("=" * 70)

    # Initialize zones
    set_custom_zones(custom_zones_data)

    cap = cv2.VideoCapture(input_video)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video file '{input_video}'")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0 or np.isnan(fps):
        fps = 25.0
        
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"\nInput: {input_video}")
    print(f"  Resolution: {width}×{height}")
    print(f"  FPS: {fps}")

    person_tracker = PersonTracker()
    zone_analytics = ZoneAnalytics(zone_keys=ZONE_KEYS, fps=fps, overcrowding_threshold=15, loitering_threshold_sec=5)

    # Use imageio with libx264 for robust web browser compatibility
    out_writer = imageio.get_writer(output_video, fps=fps, codec='libx264', macro_block_size=None)

    fourcc_avi = cv2.VideoWriter_fourcc(*'XVID')
    analysis_writer = cv2.VideoWriter(analysis_recording, fourcc_avi, fps, (width, height))
    analysis_recording_started = False
    
    # For Heatmap
    heatmap_accumulator = np.zeros((height, width), dtype=np.float32)
    bg_frame = None

    start_time = time.time()
    frame_number = 0
    
    # Cache for demographics
    demographics_cache = {}

    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        if bg_frame is None:
            bg_frame = frame.copy()

        tracked_objects = person_tracker.detect_and_track(frame)

        if not analysis_recording_started:
            analysis_recording_started = True
            analysis_start_frame = frame_number

        zone_assignments = {}
        for obj in tracked_objects:
            zone_key = get_zone(obj['centroid'])
            zone_assignments[obj['track_id']] = zone_key
            
            # Heatmap tracking: small soft circles for gradual accumulation
            cx, cy = int(obj['centroid'][0]), int(obj['centroid'][1])
            cv2.circle(heatmap_accumulator, (cx, cy), 45, 0.03, -1)
            
            # Demographics extraction
            tid = obj['track_id']
            if tid not in demographics_cache:
                x1, y1, x2, y2 = [int(v) for v in obj['bbox']]
                roi = frame[max(0, y1):min(height, y2), max(0, x1):min(width, x2)]
                color = get_dominant_color(roi)
                demo = get_mock_demographics(tid)
                demo['color'] = color
                demographics_cache[tid] = demo

        zone_counts = zone_analytics.update(frame_number, tracked_objects, zone_assignments)

        annotated = draw_zone_overlays(frame, zone_counts, analytics=zone_analytics)

        for obj in tracked_objects:
            zone_key = zone_assignments[obj['track_id']]
            annotated = draw_tracked_person(annotated, obj['track_id'],
                                            obj['bbox'], zone_key, analytics=zone_analytics,
                                            demographics=demographics_cache)

        annotated = create_hud(annotated, frame_number, fps,
                               total_frames, len(tracked_objects))

        out_writer.append_data(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB))
        if analysis_recording_started:
            analysis_writer.write(annotated)

        if frame_number % 25 == 0:
            print(f"  Frame {frame_number}/{total_frames} processed")

        frame_number += 1

    cap.release()
    out_writer.close()
    analysis_writer.release()
    
    # Generate Advanced Heatmap
    if bg_frame is not None and np.max(heatmap_accumulator) > 0:
        # Heavy blur for smooth thermal look
        blurred = cv2.GaussianBlur(heatmap_accumulator, (151, 151), 0)
        max_val = np.max(blurred)
        
        if max_val > 0:
            heatmap_norm = blurred / max_val
        else:
            heatmap_norm = blurred
            
        # Apply Jet colormap
        heatmap_colored = cv2.applyColorMap(np.uint8(255 * heatmap_norm), cv2.COLORMAP_JET)
        
        # Create an alpha mask to blend the heatmap only where people walked
        # Multiplied by 2.5 to make colors punchier, clipped to 1.0 max opacity
        alpha = np.clip(heatmap_norm * 2.5, 0, 1.0)
        alpha = np.expand_dims(alpha, axis=2)
        
        heatmap_overlay = (heatmap_colored * alpha + bg_frame * (1 - alpha)).astype(np.uint8)
        cv2.imwrite(heatmap_output, heatmap_overlay)
    else:
        cv2.imwrite(heatmap_output, np.zeros((height, width, 3), dtype=np.uint8))

    total_time = time.time() - start_time

    tracking_stats = person_tracker.get_tracking_stats()
    zone_summary = zone_analytics.get_summary()

    analytics_output = {
        "video_info": {
            "input_file": input_video,
            "resolution": f"{width}x{height}",
            "fps": fps,
            "total_frames": total_frames,
            "duration_sec": round(total_frames / fps, 2) if fps > 0 else 0,
        },
        "zones": {},
        "tracking_quality": tracking_stats,
        "performance": {
            "processing_time_sec": round(total_time, 2),
            "processing_fps": round(frame_number / total_time, 1) if total_time > 0 else 0,
        },
        "transitions": zone_analytics.get_transitions(),
        "frame_log": zone_analytics.get_frame_log()
    }

    for key in ZONE_KEYS:
        zone_info = ZONES[key]
        zone_stats = zone_summary[key]
        analytics_output["zones"][zone_info["full_name"]] = {
            "zone_key": key,
            "polygon": list(zone_info["polygon"]),
            **zone_stats,
        }

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(analytics_output, f, indent=2, ensure_ascii=False)

    with open(output_csv, 'w', encoding='utf-8') as f:
        f.write(zone_analytics.get_csv_header() + "\n")
        for row in zone_analytics.get_csv_rows():
            f.write(row + "\n")

    return analytics_output

if __name__ == "__main__":
    run_pipeline()
