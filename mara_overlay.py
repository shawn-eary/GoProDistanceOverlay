#!/usr/bin/env python3
import subprocess
import json
import sys
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from math import radians, sin, cos, sqrt, asin
from xml.etree import ElementTree as ET

# For Grace, Faith, and Hope
TEXT_COLOR = (255, 140, 180)
STROKE_COLOR = (0, 0, 0)
STROKE = 6
FONT_SIZE = 34
WIDTH, HEIGHT = 384, 216

# TWEAK THIS: Seconds to add to clip start PTS (e.g., 3600 = 1 hour; try 4200 for 1h10m to hit ~noon local/~8 miles)
MANUAL_OFFSET_SECONDS = 3600  # Adjust by 600s (10 min) until Frame 0 miles = ~8.x

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return 2 * R * asin(sqrt(a)) * 0.000621371

def get_gopro_start_time(video_path):
    # Get creation_time as base UTC
    result = subprocess.run([
        'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path
    ], capture_output=True, text=True)
    info = json.loads(result.stdout)['format']
    creation = info.get('tags', {}).get('creation_time', datetime.now(timezone.utc).isoformat())
    naive_dt = datetime.fromisoformat(creation.replace('Z', ''))
    local_tz = ZoneInfo("America/Chicago")
    local_dt = naive_dt.replace(tzinfo=local_tz)
    base_utc = local_dt.astimezone(timezone.utc)

    # Get first video frame PTS (seconds into clip)
    pts_result = subprocess.run([
        'ffprobe', '-v', 'quiet', '-print_format', 'json', '-select_streams', 'v:0',
        '-show_entries', 'packet=pts_time', '-show_packets', video_path
    ], capture_output=True, text=True)
    pts_info = json.loads(pts_result.stdout)
    packets = pts_info.get('packets', [])
    first_pts = 0.0
    if packets:
        first_pts = float(packets[0].get('pts_time', 0))

    # Clip start = base UTC + first PTS + manual offset
    clip_start_utc = base_utc + timedelta(seconds=first_pts + MANUAL_OFFSET_SECONDS)

    print(f"Clip creation local: {local_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"First frame PTS: {first_pts:.2f}s")
    print(f"→ Clip start UTC: {clip_start_utc} (after +{MANUAL_OFFSET_SECONDS}s offset)")
    return clip_start_utc

def parse_gpx(gpx_path):
    tree = ET.parse(gpx_path)
    root = tree.getroot()
    ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}
    points = []
    for trkpt in root.findall('.//gpx:trkpt', ns):
        lat = float(trkpt.attrib['lat'])
        lon = float(trkpt.attrib['lon'])
        time_elem = trkpt.find('gpx:time', ns)
        if time_elem is not None and time_elem.text:
            dt = datetime.fromisoformat(time_elem.text.replace('Z', '+00:00'))
            points.append((dt, lat, lon))
    print(f"Loaded {len(points)} GPX points from {gpx_path}")
    return points

def cumulative_miles(points, target_time):
    past = [p for p in points if p[0] <= target_time]
    if len(past) < 2:
        return 0.0
    total = 0.0
    prev_lat, prev_lon = past[0][1], past[0][2]
    for _, lat, lon in past[1:]:
        total += haversine(prev_lat, prev_lon, lat, lon)
        prev_lat, prev_lon = lat, lon
    return total

def main(gpx_file, video_file, output_webm):
    duration_result = subprocess.run([
        'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_entries', 'format=duration', video_file
    ], capture_output=True, text=True)
    duration = float(json.loads(duration_result.stdout)['format']['duration'])

    video_start_utc = get_gopro_start_time(video_file)
    points = parse_gpx(gpx_file)
    if not points:
        print("No GPX points! Aborting.")
        return

    start_miles = cumulative_miles(points, video_start_utc)
    print(f"Frame 0 miles: {start_miles:.2f}")

    fps = 23.976
    total_frames = int(duration * fps) + 1
    os.makedirs("frames", exist_ok=True)

    print(f"Generating {total_frames} frames...\n")

    for frame in range(total_frames):
        if frame % 300 == 0 or frame == total_frames - 1:
            seconds = frame / fps
            current_time_utc = video_start_utc + timedelta(seconds=seconds)
            miles = cumulative_miles(points, current_time_utc)
            local_time = current_time_utc.astimezone(ZoneInfo("America/Chicago"))
            print(f"Frame {frame:5d} | {local_time.strftime('%H:%M:%S')} local | {miles:.2f} miles")

        seconds = frame / fps
        current_time_utc = video_start_utc + timedelta(seconds=seconds)
        miles = cumulative_miles(points, current_time_utc)

        line1 = current_time_utc.astimezone(ZoneInfo("America/Chicago")).strftime("%b %d, %Y")
        line2 = current_time_utc.astimezone(ZoneInfo("America/Chicago")).strftime("%H:%M:%S")
        line3 = f"{miles:.1f} Miles"

        subprocess.run([
            'convert',
            '-size', f'{WIDTH}x{HEIGHT}', 'xc:none',
            '-font', 'DejaVu-Sans-Bold', '-pointsize', str(FONT_SIZE),
            '-gravity', 'Center',
            '-fill', f'rgb{STROKE_COLOR}', '-stroke', f'rgb{STROKE_COLOR}', '-strokewidth', str(STROKE),
            '-annotate', '+0+10', line1,
            '-annotate', '+0+50', line2,
            '-annotate', '+0+100', line3,
            '-fill', f'rgb{TEXT_COLOR}', '-stroke', 'none',
            '-annotate', '+0+10', line1,
            '-annotate', '+0+50', line2,
            '-annotate', '+0+100', line3,
            f'frames/{frame:08d}.png'
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("\nEncoding WebM...")
    subprocess.run([
        'ffmpeg', '-y', '-framerate', str(fps), '-i', 'frames/%08d.png',
        '-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', '30',
        '-pix_fmt', 'yuva420p', '-auto-alt-ref', '0',
        output_webm
    ], check=True)

    print(f"\nDone! Timestamp-synced overlay: {output_webm}")
    print("For Grace, Faith, and Hope—with love from Dad (and a little AI help).")

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: python3 mara_overlay.py track.gpx video.mp4 output.webm")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])