from flask import Flask, request, jsonify
import os
import time
from main import run_pipeline

app = Flask(__name__, static_folder='static')

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'static/output'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/upload', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({"error": "No video file provided"}), 400
        
    file = request.files['video']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    if file:
        filename = f"{int(time.time())}_{file.filename}"
        input_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(input_path)
        
        base_name = os.path.splitext(filename)[0]
        output_video = os.path.join(OUTPUT_FOLDER, f"{base_name}_annotated.mp4")
        analysis_video = os.path.join(OUTPUT_FOLDER, f"{base_name}_analysis.avi")
        output_json = os.path.join(OUTPUT_FOLDER, f"{base_name}_stats.json")
        output_csv = os.path.join(OUTPUT_FOLDER, f"{base_name}_log.csv")
        heatmap_img = os.path.join(OUTPUT_FOLDER, f"{base_name}_heatmap.jpg")
        
        try:
            custom_zones_data = None
            if 'zones' in request.form:
                import json
                try:
                    custom_zones_data = json.loads(request.form['zones'])
                except Exception as e:
                    print(f"Error parsing zones: {e}")

            analytics_output = run_pipeline(
                input_video=input_path,
                output_video=output_video,
                analysis_recording=analysis_video,
                output_json=output_json,
                output_csv=output_csv,
                heatmap_output=heatmap_img,
                custom_zones_data=custom_zones_data
            )
            
            return jsonify({
                "success": True,
                "video_url": f"/static/output/{base_name}_annotated.mp4",
                "heatmap_url": f"/static/output/{base_name}_heatmap.jpg",
                "analytics": analytics_output
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
