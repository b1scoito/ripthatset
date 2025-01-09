import asyncio
import tempfile
from pathlib import Path
from typing import Dict

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)

from ripthatset.config import ProcessingConfig, ShazamConfig, TrackMatchConfig
from ripthatset.models import TrackMatch
from ripthatset.models.progress import ProgressTracker
from ripthatset.shazam import FastShazam
from ripthatset.utils import calculate_optimal_batch_size, split_audio

console = Console()


async def recognize_segment(
    shazam: FastShazam,
    segment_path: Path,
    segment_number: int,
    segment_length: int,
) -> Dict | None:
    """Process a single audio segment."""
    try:
        with open(segment_path, "rb") as f:
            audio_bytes = f.read()

        result = await shazam.recognize(audio_bytes)

        if result and isinstance(result, dict):
            if result.get("matches"):
                timestamp = segment_number * (segment_length / 1000)
                minutes = int(timestamp // 60)
                seconds = int(timestamp % 60)
                result["segment_number"] = segment_number
                result["timestamp"] = timestamp
                return result
        return None

    except Exception as e:
        console.print(
            f"[#E5C07B]⚠ Error recognizing segment {segment_number + 1}: {str(e)}[/#E5C07B]"
        )
        return None


async def process_segments(
    audio_path: Path,
    shazam_config: ShazamConfig,
    track_config: TrackMatchConfig,
    process_config: ProcessingConfig,
) -> Dict:
    """Process audio file and identify tracks."""
    shazam = FastShazam(shazam_config)
    results = {}
    track_matches = {}
    segment_length = process_config.segment_length

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        console.print(
            "[#E5C07B]Splitting audio file into segments using FFmpeg...[/#E5C07B]"
        )
        segment_files = split_audio(
            audio_path,
            temp_path,
            segment_length / 1000,
        )

        total_segments = len(segment_files)
        batch_size = process_config.batch_size or calculate_optimal_batch_size(
            total_segments, process_config.cpu_count
        )

        console.print(
            f"[#E5C07B]Processing {total_segments} segments in batches of {batch_size}...[/#E5C07B]"
        )

        progress_tracker = ProgressTracker(total_segments)

        progress = Progress(
            "✨ ",
            SpinnerColumn("dots"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(complete_style="#98C379", finished_style="#98C379"),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=True,
            expand=True,
        )

        with progress:
            task = progress.add_task(
                "[#E5C07B]Analyzing segments...", total=total_segments
            )

            for i in range(0, len(segment_files), batch_size):
                batch = segment_files[i : i + batch_size]
                tasks = []

                for j, segment_path in enumerate(batch):
                    segment_number = i + j
                    tasks.append(
                        recognize_segment(
                            shazam,
                            segment_path,
                            segment_number,
                            segment_length,
                        )
                    )

                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for j, result in enumerate(batch_results):
                    segment_number = i + j
                    timestamp = segment_number * (segment_length / 1000)
                    minutes = int(timestamp // 60)
                    seconds = int(timestamp % 60)

                    if isinstance(result, dict) and result.get("matches"):
                        results[segment_number] = result
                        track = result["track"]
                        track_id = track["key"]
                        confidence = (
                            result.get("matches", [{}])[0].get("score", 100) / 100
                        )

                        if track_id not in track_matches:
                            track_matches[track_id] = TrackMatch(
                                track_id=track_id,
                                title=track["title"],
                                artist=track["subtitle"],
                                confidence=confidence,
                                config=track_config,
                            )

                        track_matches[track_id].add_segment(segment_number)

                        progress_tracker.update(success=True)
                        console.print(
                            f"[#98C379]◆ Found [{minutes:02d}:{seconds:02d}] (segment {segment_number + 1}): "
                            f"{track['subtitle']} - {track['title']}[/#98C379]",
                            highlight=False,
                        )
                    else:
                        progress_tracker.update(success=False)
                        console.print(
                            f"[#7F848E]○ No match [{minutes:02d}:{seconds:02d}] "
                            f"(segment {segment_number + 1})[/#7F848E]",
                            highlight=False,
                        )

                    progress.update(task, advance=1)

        await asyncio.sleep(0.1)

        console.print()
        console.print(progress_tracker.format_progress())

        valid_tracks = {}
        for track_id, match in track_matches.items():
            if match.is_valid:
                track_dict = match.to_dict()
                track_dict["timestamp"] = track_dict["segment_number"] * (
                    segment_length / 1000
                )
                valid_tracks[track_id] = track_dict

        await shazam.close()

    return {
        "full_results": results,
        "tracklist": valid_tracks,
        "total_segments": total_segments,
        "detected_tracks": len(valid_tracks),
        "success_rate": (len(results) / total_segments) * 100
        if total_segments > 0
        else 0,
    }
