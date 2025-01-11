import os
import subprocess
from pathlib import Path
from typing import List


def split_audio(
    audio_path: Path,
    output_dir: Path,
    segment_duration: float,
    pattern: str = "segment_%03d.wav",  # Updated to padded numbering for correct sorting
) -> List[Path]:
    """
    Split audio file into segments using ffmpeg.

    Args:
        audio_path: Path to input audio file
        output_dir: Directory for output segments
        segment_duration: Duration of each segments in seconds
        pattern: Naming pattern for segments

    Returns:
        List of paths to created segments
    """
    segment_pattern = os.path.join(output_dir, pattern)

    subprocess.run(
        [
            "ffmpeg",
            "-i",
            str(audio_path),
            "-f",
            "segment",
            "-segment_time",
            str(segment_duration),
            "-acodec",
            "pcm_s16le",
            "-ar",
            "44100",
            segment_pattern,
            "-loglevel",
            "quiet",
        ],
        check=True,
    )

    # Ensure natural sorting of segments using zero-padded numbers
    return sorted(
        Path(output_dir).glob("segment_*.wav"), key=lambda p: int(p.stem.split("_")[1])
    )


def calculate_optimal_batch_size(
    total_segments: int, cpu_count: int | None = None
) -> int:
    """
    Calculate optimal batch size based on total segments and system resources.

    Args:
        total_segments: Total number of segments to process
        cpu_count: Number of CPU cores to use (if None, uses system count)

    Returns:
        Optimal batch size for processing
    """
    if cpu_count is None:
        cpu_count = os.cpu_count() or 2

    # Base calculation
    if total_segments < 100:
        base_size = min(10, max(5, total_segments // 10))
    elif total_segments < 500:
        base_size = min(20, max(10, cpu_count * 3))
    else:
        base_size = min(30, max(15, cpu_count * 2))

    # Adjust for high segment-to-CPU ratios
    segments_per_cpu = total_segments / cpu_count
    if segments_per_cpu > 100:
        base_size = min(50, base_size * 1.5)

    # Final adjustments
    batch_size = int(
        min(
            base_size,
            total_segments * 0.1,  # Don't exceed 10% of total segments
            50,  # Hard cap at 50
        )
    )

    return max(5, batch_size)  # Never go below 5
