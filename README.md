# Real-Time People Tracking & Zone-Based Occupancy Analytics

A full-stack computer vision system that detects and tracks people in video footage using **YOLOv8** and **DeepSORT**, assigns them to custom spatial zones, and produces rich per-zone analytics including occupancy, dwell time, entry/exit counts, and zone transitions — all presented through a premium **Analytics Pro** web dashboard.

---

##  Features

- **YOLOv8n Person Detection** — Fast, real-time person detection
- **DeepSORT Multi-Object Tracking** — Persistent IDs across frames, robust to occlusion
- **Custom Zone Drawing** — Interactive canvas UI to draw polygon zones over your video frame
- **Restricted Area Alerts** — Mark any zone as "Restricted" and get instant intrusion alerts
- **Live Analytics Dashboard** — Occupancy line charts, zone distribution doughnut, dwell time bar charts
- **Heatmap Generation** — Thermal overlay showing where people spent the most time
- **Trajectory Trails** — Comet-tail visual showing each person's movement path
- **Loitering & Overcrowding Alerts** — Real-time toast notifications during video review
- **PDF Export** — Download the entire dashboard as a PDF report

---

## Project Structure

```
├── app.py                  # Flask web server & API routes
├── main.py                 # Core pipeline orchestrator
├── tracker.py              # YOLOv8 + DeepSORT tracking logic
├── zones.py                # Zone definition, geometry, and visual overlay
├── analytics.py            # Per-zone analytics engine
├── requirements.txt        # Python dependencies
├── static/
│   ├── index.html          # Frontend UI (Analytics Pro Dashboard)
│   ├── styles.css          # Glassmorphism dark theme
│   └── script.js           # Chart.js, zone drawing, and alert logic
└── .gitignore
```

---

## Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/locini13/Real-Time-People-Tracking-Zone-Based-Occupancy-Analytics.git
cd Real-Time-People-Tracking-Zone-Based-Occupancy-Analytics
```

### 2. Create and Activate a Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
pip install imageio[ffmpeg]
```
> **Note:** The `yolov8n.pt` model weights (~6MB) will be auto-downloaded from Ultralytics on first run.

### 4. Run the Application
```bash
python app.py
```
Open your browser at **http://localhost:5000**

---

## Zone Layout

Zones are drawn interactively via the web UI canvas. The system supports any number of custom polygon zones. A typical 4-zone layout for an overhead concourse scene looks like this:

| Zone | Area | Purpose |
|------|------|---------|
| Zone 0 | Top-Left quadrant | Entry corridor |
| Zone 1 | Top-Right quadrant | Waiting area |
| Zone 2 | Bottom-Left quadrant | Transit passage |
| Zone 3 | Bottom-Right quadrant | Exit corridor |

> Draw zones by clicking on the canvas frame in the UI after uploading your video. Each click adds a polygon vertex. Click "Complete Zone" to finalize the shape.

---

##  Parameter Choices & Rationale

### YOLOv8 Detection
| Parameter | Value | Reason |
|-----------|-------|--------|
| `model` | `yolov8n.pt` | Nano model — fast inference for real-time processing |
| `conf` | `0.25` | Lower than default (0.5) to avoid missing people in grayscale/overhead footage |
| `iou` | `0.45` | Standard NMS threshold to prevent duplicate boxes |
| `classes` | `[0]` (person only) | Filters out all non-person detections for clean output |

### DeepSORT Tracking
| Parameter | Value | Reason |
|-----------|-------|--------|
| `max_age` | `150` frames (6s) | Remembers a lost person for 6 seconds — covers occlusions, crowd crossings |
| `n_init` | `3` | Requires 3 consecutive detections to confirm a track — prevents phantom tracks from shadows |
| `max_iou_distance` | `0.9` | Permissive movement gating — handles fast walkers and camera jitter |
| `max_cosine_distance` | `0.5` | Flexible appearance matching — accounts for lighting changes in overhead footage |
| `nn_budget` | `100` | Stores 100 appearance descriptors per track for robust re-identification |
| `embedder` | `mobilenet` | Fast, discriminative appearance features even on grayscale input |

---

##  Zone Boundary Logic

**Rule:** A person is assigned to a zone based solely on the **centroid** (center point) of their bounding box.

**Why:** A bounding box can physically overlap multiple zones simultaneously. Using a single centroid point ensures every person belongs to **exactly one zone** at any frame — no ambiguity, no double-counting. This is applied consistently across every frame in `zones.py → get_zone()`.

---

##  Sample Output

### Analytics Summary (`analytics_summary.json`)
```json
{
  "zones": {
    "Zone 0 - Entrance": {
      "total_unique_visitors": 18,
      "average_dwell_time_sec": 4.2,
      "peak_occupancy": 6,
      "entries": 20,
      "exits": 18
    }
  },
  "transitions": {
    "0->1": 12,
    "1->2": 9,
    "2->3": 14
  }
}
```

### Frame Log (`occupancy_log.csv`)
```
frame,timestamp_sec,zone_0_count,zone_1_count,zone_2_count,zone_3_count,total_count
0,0.0,2,3,1,4,10
25,1.0,3,2,2,3,10
```

---

## Challenges & Solutions

### 1. ID Switches During Occlusions
**Challenge:** When two people crossed paths or walked close together, DeepSORT would lose track of one and assign a new ID — inflating unique visitor counts and breaking zone transition records.

**Solution:** Significantly tuned `max_age` from 30 → 150 frames and relaxed `max_cosine_distance` from 0.3 → 0.5. This allows the tracker to "remember" a lost person for 6 seconds and successfully re-identify them when they re-emerge. ID switch count is logged in the `tracking_quality` field of the JSON summary.

### 2. Zone Boundary Ambiguity
**Challenge:** Large bounding boxes (especially for people near zone edges) could span multiple zones.

**Solution:** Adopted the **centroid rule** — only the center point of a bounding box determines zone membership. This is a mathematically deterministic rule with zero ambiguity applied consistently in all frames.

### 3. Performance vs. Quality Tradeoff
**Challenge:** Running YOLOv8 + DeepSORT on every frame of a full HD video is CPU-intensive.

**Solution:** Used `yolov8n` (Nano) for fast inference while maintaining sufficient accuracy for overhead crowd footage. The pipeline processes frames sequentially at the video's native FPS. For production deployment, a task queue (e.g., Celery + Redis) is recommended to prevent HTTP timeout on long videos.

### 4. Re-entry Not Double-Counted
**Challenge:** A visitor who leaves and re-enters a zone should count as one unique visitor, not two.

**Solution:** The `unique_visitors` set in `analytics.py` uses Python `set.add()` — adding the same `track_id` twice has no effect. Only the first entry per person per zone is counted.

---

## Dependencies

```
ultralytics>=8.0.0       # YOLOv8
deep-sort-realtime>=1.3.2 # DeepSORT tracker
opencv-python>=4.8.0     # Video processing
numpy>=1.24.0            # Numerical operations
flask>=3.0.0             # Web server
imageio[ffmpeg]          # Browser-compatible MP4 encoding
```

---

## Output Deliverables

| File | Description |
|------|-------------|
| `static/output/*_annotated.mp4` | Annotated video with bounding boxes, track IDs, zone overlays |
| `static/output/*_stats.json` | Structured per-zone analytics summary |
| `static/output/*_log.csv` | Frame-by-frame occupancy log |
| `static/output/*_heatmap.jpg` | Thermal heatmap overlay |
