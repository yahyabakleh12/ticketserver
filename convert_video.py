# import ffmpeg
# import os
# def make_browser_friendly(input_path, output_path):
#     if os.path.isfile(input_path):
#             print("Valid")
#     else:
#             print("Not Valid")
#     (
#         ffmpeg
#         .input(input_path)
#         .output(output_path, c_v='libx264', preset='fast', crf=23, movflags='+faststart', c_a='aac')
#         .run(overwrite_output=True)
#     )

# make_browser_friendly("D:/exit_video/0dc88677-eabf-4752-9160-08a738e9621b.mp4", "test/good_video.mp4")

import os
import ffmpeg

# Set path to ffmpeg.exe explicitly
os.environ["PATH"] += os.pathsep + r"C:/ffmpeg/bin/ffmpeg.exe"

def make_browser_friendly(input_path, output_path):
    (
        ffmpeg
        .input(input_path)
        .output(output_path, vcodec='libx264', preset='fast', crf=23, movflags='+faststart', acodec='aac')
        .run(overwrite_output=True)
    )
import subprocess

def make_browser_friendly(input_path, output_path):
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-movflags", "+faststart",
        "-c:a", "aac",
        output_path
    ]
    subprocess.run(cmd, check=True)

make_browser_friendly(
    "test/0bbc1335-004b-44c3-bf23-d53292f798e4.mp4",
    "test/0bbc1335-004b-44c3-bf23-d53292f798e41.mp4"
)
# make_browser_friendly(
#     "D:/exit_video/0dc88677-eabf-4752-9160-08a738e9621b.mp4",
#     "test/good_video.mp4"
# )
