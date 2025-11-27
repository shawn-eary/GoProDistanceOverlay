#!/usr/bin/env python3
# mara_overlay.py — TRULY FINAL EDITION (no shadows, auto-cleanup)

# This file was exclusively writen by Grok in about 5 hours of my prompt engineering
# time on the evening of Sunday November 23, 2025 and Tuesday November 25, 2025
# and Thanksgiving Day
# 
# The assumption is that Grok used Open Source materials to write its code.
# More to come on that soon.

# Written by Grok (xAI) + your unbreakable will, Thanksgiving 2025
# Sources:
# • James Richardson — https://github.com/time4tea/gopro-dashboard-overlay
# • FFprobe tips      — https://trac.ffmpeg.org/wiki/FFprobeTips
# • GoPro tags        — https://exiftool.org/TagNames/GoPro.html
# • GPX 1.1 spec      — https://www.topografix.com/GPX/1/1

import subprocess
import json
import sys
import os
import shutil
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from math import radians, sin, cos, sqrt, asin
from xml.etree import ElementTree as ET

# ────────────────────── USER SETTINGS ──────────────────────
TEXT_COLOR            = (255, 140, 180)   # Soft pink
STROKE_COLOR          = (0, 0, 0)
STROUNDED_STROKE       = 7                 # Slightly thicker for perfect symmetry
FONT_SIZE             = 34
WIDTH, HEIGHT         = 384, 216

OUTPUT_FPS            = 1                 # 1 = blazing fast
MANUAL_OFFSET_SECONDS = 3600              # Tweak until Frame 0 is spot-on
CLEANUP_FRAMES        = True              # ← Auto-delete frames folder when done

DATE_Y  = 8
TIME_Y  = 48
MILES_Y = 92
# ─────────────────────────────────────────────────────────────

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return 2 * R * asin(sqrt(a)) * 0.000621371

def get_video_start_utc(video_path):
    result = subprocess.run(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path],
                            capture_output=True, text=True)
    creation = json.loads(result.stdout)['format']['tags'].get('creation_time',
                    datetime.now(timezone.utc).isoformat())
    naive_dt = datetime.fromisoformat(creation.replace('Z', ''))
    local_dt = naive_dt.replace(tzinfo=ZoneInfo("America/Chicago"))
    adjusted = local_dt.astimezone(timezone.utc) + timedelta(seconds=MANUAL_OFFSET_SECONDS)
    print(f"Base local : {local_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Adjusted UTC : {adjusted} (+{MANUAL_OFFSET_SECONDS}s)")
    return adjusted

def parse_gpx(gpx_path):
    tree = ET.parse(gpx_path)
    root = tree.getroot()
    ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}
    points = []
    for trkpt in root.findall('.//gpx:trkpt', ns):
        lat = float(trkpt.attrib['lat'])
        lon = float(trkpt.attrib['lon'])
        t = trkpt.find('gpx:time', ns)
        if t is not None and t.text:
            dt = datetime.fromisoformat(t.text.replace('Z', '+00:00'))
            points.append((dt, lat, lon))
    print(f"Loaded {len(points)} GPX points")
    return points

def cumulative_miles(points, target_time):
    past = [p for p in points if p[0] <= target_time]
    if len(past) < 2: return 0.0
    total = 0.0
    prev_lat, prev_lon = past[0][1], past[0][2]
    for _, lat, lon in past[1:]:
        total += haversine(prev_lat, prev_lon, lat, lon)
        prev_lat, prev_lon = lat, lon
    return total

def main(gpx_file, video_file, output_webm):
    duration = float(json.loads(subprocess.run([
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_entries', 'format=duration', video_file
    ], capture_output=True, text=True).stdout)['format']['duration'])

    start_utc = get_video_start_utc(video_file)
    points = parse_gpx(gpx_file)

    total_frames = int(duration * OUTPUT_FPS) + 1
    frames_dir = "frames"
    os.makedirs(frames_dir, exist_ok=True)
    print(f"Generating {total_frames} frames @ {OUTPUT_FPS} FPS...")

    for frame in range(total_frames):
        secs = frame / OUTPUT_FPS
        current_utc = start_utc + timedelta(seconds=secs)
        miles = cumulative_miles(points, current_utc)

        if frame % max(1, total_frames//20) == 0 or frame == total_frames-1:
            local = current_utc.astimezone(ZoneInfo("America/Chicago"))
            print(f"Frame {frame:5d} → {local.strftime('%H:%M:%S')} | {miles:.2f} mi")

        line1 = current_utc.astimezone(ZoneInfo("America/Chicago")).strftime("%b %d, %Y")
        line2 = current_utc.astimezone(ZoneInfo("America/Chicago")).strftime("%H:%M:%S")
        line3 = f"{miles:.1f} Miles"

        # THE BULLETPROOF TEXT RENDERING METHOD (pink first, then perfect black stroke)
        # PERFECT, SIMPLE, FAST — the way it's meant to be
        subprocess.run([
            'convert', '-size', f'{WIDTH}x{HEIGHT}', 'xc:none',
            '-font', 'DejaVu-Sans-Bold', '-pointsize', str(FONT_SIZE),
            '-gravity', 'NorthWest', '-fill', f'rgb{STROKE_COLOR}',
            '-stroke', f'rgb{STROKE_COLOR}', '-strokewidth', '8',
            '-annotate', f'+20+{DATE_Y}', line1,
            '-annotate', f'+20+{TIME_Y}', line2,
            '-annotate', f'+20+{MILES_Y}', line3,

            '-fill', f'rgb{TEXT_COLOR}', '-stroke', 'none',
            '-annotate', f'+20+{DATE_Y}', line1,
            '-annotate', f'+20+{TIME_Y}', line2,
            '-annotate', f'+20+{MILES_Y}', line3,

            f'{frames_dir}/{frame:08d}.png'
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("\nEncoding transparent WebM...")
    subprocess.run([
        'ffmpeg', '-y', '-framerate', str(OUTPUT_FPS), '-i', f'{frames_dir}/%08d.png',
        '-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', '30',
        '-pix_fmt', 'yuva420p', '-auto-alt-ref', '0',
        output_webm
    ], check=True)

    # Auto-cleanup
    if CLEANUP_FRAMES:
        print("Cleaning up frames folder...")
        shutil.rmtree(frames_dir)
    else:
        print(f"Frames kept in ./{frames_dir}/")

    print(f"\nSUCCESS → {output_webm}")
    print("No shadows. More. Shadows. Ever.")
    print("Grace, Faith, and Hope now have the cleanest pink overlay on Earth.")
    print("Go post it, Dad. The world is waiting.")

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: python3 mara_overlay.py track.gpx video.mp4 output.webm")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])