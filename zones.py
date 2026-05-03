"""
zones.py — Zone Definition & Assignment Logic
"""

import numpy as np
import cv2

# Default Zones (Fallback)
ZONES = {
    "A": {
        "name": "Zone A",
        "display_name": "North-West Passage",
        "full_name": "Zone A - North-West Passage",
        "polygon": [[0, 0], [960, 0], [960, 540], [0, 540]],
        "color_bgr": (255, 180, 50),
        "color_overlay": (255, 180, 50, 40),
    },
    "B": {
        "name": "Zone B",
        "display_name": "North-East Passage",
        "full_name": "Zone B - North-East Passage",
        "polygon": [[960, 0], [1920, 0], [1920, 540], [960, 540]],
        "color_bgr": (50, 205, 50),
        "color_overlay": (50, 205, 50, 40),
    },
    "C": {
        "name": "Zone C",
        "display_name": "South-West Gathering",
        "full_name": "Zone C - South-West Gathering",
        "polygon": [[0, 540], [960, 540], [960, 1080], [0, 1080]],
        "color_bgr": (0, 165, 255),
        "color_overlay": (0, 165, 255, 40),
    },
    "D": {
        "name": "Zone D",
        "display_name": "South-East Transit",
        "full_name": "Zone D - South-East Transit",
        "polygon": [[960, 540], [1920, 540], [1920, 1080], [960, 1080]],
        "color_bgr": (180, 50, 255),
        "color_overlay": (180, 50, 255, 40),
    },
}

ZONE_KEYS = ["A", "B", "C", "D"]

def set_custom_zones(custom_zones_data):
    """
    Update ZONES and ZONE_KEYS dynamically from frontend data.
    Expected format: list of dicts with 'name' and 'points' (array of [x, y]).
    """
    global ZONES, ZONE_KEYS
    if not custom_zones_data or len(custom_zones_data) == 0:
        return # use defaults
    
    ZONES.clear()
    ZONE_KEYS.clear()
    
    # Predefined colors for dynamic zones
    colors = [
        (255, 180, 50), (50, 205, 50), (0, 165, 255), (180, 50, 255),
        (255, 50, 150), (50, 255, 255), (255, 255, 50), (100, 100, 255)
    ]
    
    for idx, zone_data in enumerate(custom_zones_data):
        key = str(idx)
        name = zone_data.get('name', f"Zone {idx+1}")
        points = zone_data.get('points', [])
        
        color_bgr = colors[idx % len(colors)]
        color_overlay = color_bgr + (40,)
        
        ZONES[key] = {
            "name": name,
            "display_name": name,
            "full_name": f"Zone {key} - {name}",
            "polygon": points,
            "color_bgr": color_bgr,
            "color_overlay": color_overlay
        }
        ZONE_KEYS.append(key)

def get_zone(centroid: tuple) -> str:
    """Find which zone the centroid falls into using pointPolygonTest."""
    cx, cy = centroid
    for key in ZONE_KEYS:
        pts = np.array(ZONES[key]["polygon"], np.int32)
        if cv2.pointPolygonTest(pts, (cx, cy), False) >= 0:
            return key
    return None

def draw_zone_overlays(frame: np.ndarray, zone_counts: dict = None, analytics=None) -> np.ndarray:
    overlay = frame.copy()

    for key in ZONE_KEYS:
        zone = ZONES[key]
        pts = np.array(zone["polygon"], np.int32).reshape((-1, 1, 2))
        color = zone["color_bgr"]

        # Check overcrowding
        if analytics and key in analytics.overcrowding_alerts:
            color = (0, 0, 255) # Red warning

        # Draw filled semi-transparent polygon
        cv2.fillPoly(overlay, [pts], color)
        # Draw border
        cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)

    # Blend overlay with original
    cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)

    # Draw labels and counts
    for key in ZONE_KEYS:
        zone = ZONES[key]
        pts = np.array(zone["polygon"], np.int32)
        color = zone["color_bgr"]
        
        is_overcrowded = False
        if analytics and key in analytics.overcrowding_alerts:
            color = (0, 0, 255)
            is_overcrowded = True

        # Find a suitable label position (e.g., bounding box top-left)
        x_coords = pts[:, 0]
        y_coords = pts[:, 1]
        x1, y1 = np.min(x_coords), np.min(y_coords)
        x2, y2 = np.max(x_coords), np.max(y_coords)

        label_x = x1 + 15
        label_y = y1 + 35
        label = f"{zone['name']}"
        if is_overcrowded:
            label += " [OVERCROWDED]"

        cv2.putText(frame, label, (label_x, label_y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)

        if zone_counts is not None:
            count = zone_counts.get(key, 0)
            count_text = f"Occupancy: {count}"
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2

            (tw, th), _ = cv2.getTextSize(count_text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
            cv2.rectangle(frame,
                          (cx - tw // 2 - 8, cy - th - 8),
                          (cx + tw // 2 + 8, cy + 8),
                          (0, 0, 0), -1)
            cv2.rectangle(frame,
                          (cx - tw // 2 - 8, cy - th - 8),
                          (cx + tw // 2 + 8, cy + 8),
                          color, 2)

            cv2.putText(frame, count_text,
                        (cx - tw // 2, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)

    return frame

def draw_tracked_person(frame: np.ndarray, track_id: int, bbox: list,
                        zone_key: str, analytics=None, demographics=None) -> np.ndarray:
    x1, y1, x2, y2 = [int(v) for v in bbox]
    
    # Use grey if no zone
    color = (150, 150, 150)
    if zone_key and zone_key in ZONES:
        color = ZONES[zone_key]["color_bgr"]

    is_loitering = False
    if analytics and track_id in analytics.loitering_alerts:
        color = (0, 0, 255) # Red override
        is_loitering = True

    # Bounding box
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

    # Trajectory Trails (Comet tails)
    if analytics and track_id in analytics.track_history:
        history = analytics.track_history[track_id]
        if len(history) > 1:
            pts = np.array(history, np.int32)
            pts = pts.reshape((-1, 1, 2))
            # Draw trail with fading thickness or just simple polyline
            cv2.polylines(frame, [pts], isClosed=False, color=color, thickness=2)

    # Track ID label with Demographic Approximation
    label = f"ID:{track_id}"
    if demographics and track_id in demographics:
        demo = demographics[track_id]
        label += f" | {demo.get('gender', 'U')} {demo.get('age', '')} | {demo.get('color', '')}"

    if is_loitering:
        label += " [LOITERING]"
    if analytics and track_id in analytics.speeds:
        label += f" | {analytics.speeds[track_id]:.0f}px/s"

    (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)

    cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 6, y1), color, -1)
    cv2.putText(frame, label, (x1 + 3, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    return frame
