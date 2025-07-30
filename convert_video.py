import os
import subprocess


def make_browser_friendly(input_path: str) -> str:
    """Convert a video to a browser friendly format in the same directory.

    Parameters
    ----------
    input_path : str
        Absolute path to the video.

    Returns
    -------
    str
        Path to the converted video. The original file is removed.
    """
    directory, filename = os.path.split(input_path)
    base, ext = os.path.splitext(filename)
    output_path = os.path.join(directory, f"{base}_bf{ext}")

    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-movflags", "+faststart",
        "-c:a", "aac",
        output_path,
    ]

    subprocess.run(cmd, check=True)

    os.remove(input_path)
    return output_path

