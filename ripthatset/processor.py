import asyncio
import tempfile
from pathlib import Path
from typing import Dict, Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)

from ripthatset.acrcloud.client import ACRCloudClient
from ripthatset.config import (
    ACRCloudConfig,
    ProcessingConfig,
    ShazamConfig,
    TrackMatchConfig,
)
from ripthatset.models import TrackMatch
from ripthatset.models.progress import ProgressTracker
from ripthatset.shazam import FastShazam
from ripthatset.utils import calculate_optimal_batch_size, split_audio

console = Console()


async def recognize_segment(
    shazam: FastShazam,
    acrcloud: Optional[ACRCloudClient],
    segment_path: Path,
    segment_number: int,
    segment_length: int,
) -> Dict | None:
    """Process a single audio segment using Shazam and optionally ACRCloud as fallback."""
    try:
        timestamp = segment_number * (segment_length / 1000)
        hours = int(timestamp // 3600)
        minutes = int((timestamp % 3600) // 60)
        seconds = int(timestamp % 60)
        timestamp_str = (
            f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            if hours > 0
            else f"{minutes:02d}:{seconds:02d}"
        )

        # Read audio data once
        with open(segment_path, "rb") as f:
            audio_bytes = f.read()

        # Try Shazam first
        try:
            result = await shazam.recognize(audio_bytes)
            if result and isinstance(result, dict) and result.get("matches"):
                track = result["track"]
                result["segment_number"] = segment_number
                result["timestamp"] = timestamp
                result["source"] = "shazam"
                return result
        except Exception as e:
            console.print(
                f"[#E5C07B]⚠ Shazam error for segment {segment_number + 1}: {str(e)}[/#E5C07B]",
                highlight=False,
            )

        # If Shazam failed and ACRCloud is available, try it
        if acrcloud and audio_bytes:
            try:
                console.print(
                    f"[#7F848E]◇ Fallback ACRCloud for segment {segment_number + 1}...[/#7F848E]",
                    highlight=False,
                )
                acr_result = await acrcloud.recognize(audio_bytes)

                if isinstance(acr_result, dict) and acr_result.get("matches"):
                    track = acr_result["track"]
                    # Format ACRCloud result to match Shazam structure
                    result = {
                        "matches": acr_result["matches"],
                        "track": track,
                        "segment_number": segment_number,
                        "timestamp": timestamp,
                        "source": "acrcloud",
                    }
                    return result
            except Exception as e:
                console.print(
                    f"[#E5C07B]⚠ ACRCloud error for segment {segment_number + 1}: {str(e)}[/#E5C07B]",
                    highlight=False,
                )

        # No match from either service
        console.print(
            f"[#7F848E]○ No match [{timestamp_str}] "
            f"(segment {segment_number + 1})[/#7F848E]",
            highlight=False,
        )
        return None

    except Exception as e:
        console.print(
            f"[#E5C07B]⚠ Error recognizing segment {segment_number + 1}: {str(e)}[/#E5C07B]",
            highlight=False,
        )
        return None


async def process_segments(
    audio_path: Path,
    shazam_config: ShazamConfig,
    track_config: TrackMatchConfig,
    process_config: ProcessingConfig,
    acrcloud_config: Optional[ACRCloudConfig] = None,
) -> Dict:
    """Process audio file and identify tracks."""
    shazam = FastShazam(shazam_config)
    acrcloud = ACRCloudClient(acrcloud_config) if acrcloud_config else None
    results = {}
    track_matches = {}
    segment_length = process_config.segment_length

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        console.print(
            "[#E5C07B]Splitting audio file into segments using FFmpeg...[/#E5C07B]"
        )
        segment_files = sorted(
            split_audio(
                audio_path,
                temp_path,
                segment_length / 1000,
            )
        )

        total_segments = len(segment_files)
        batch_size = process_config.batch_size or calculate_optimal_batch_size(
            total_segments, process_config.cpu_count
        )

        service_info = "Shazam + ACRCloud" if acrcloud else "Shazam"
        console.print(
            f"[#E5C07B]Processing {total_segments} segments in batches of {batch_size} using {service_info}...[/#E5C07B]"
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
                            shazam=shazam,
                            acrcloud=acrcloud,
                            segment_path=segment_path,
                            segment_number=segment_number,
                            segment_length=segment_length,
                        )
                    )

                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for j, result in enumerate(batch_results):
                    segment_number = i + j
                    timestamp = segment_number * (segment_length / 1000)
                    hours = int(timestamp // 3600)
                    minutes = int((timestamp % 3600) // 60)
                    seconds = int(timestamp % 60)
                    timestamp_str = (
                        f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                        if hours > 0
                        else f"{minutes:02d}:{seconds:02d}"
                    )

                    if isinstance(result, dict) and result.get("matches"):
                        results[segment_number] = result
                        track = result["track"]
                        track_id = track["key"]
                        confidence = (
                            result.get("matches", [{}])[0].get("score", 100) / 100
                        )
                        source = result.get("source", "shazam")

                        if track_id not in track_matches:
                            track_matches[track_id] = TrackMatch(
                                track_id=track_id,
                                title=track["title"],
                                artist=track["subtitle"],
                                confidence=confidence,
                                config=track_config,
                                source=source,
                            )

                        track_matches[track_id].add_segment(segment_number)
                        progress_tracker.update(success=True)

                        # Use different symbols for different sources
                        symbol = "◆" if source == "shazam" else "◇"
                        console.print(
                            f"[#98C379]{symbol} Found [{timestamp_str}] (segment {segment_number + 1}): "
                            f"{track['subtitle']} - {track['title']}[/#98C379] "
                            f"[#7F848E]via {source}[/#7F848E]",
                            highlight=False,
                        )
                    else:
                        progress_tracker.update(success=False)
                        console.print(
                            f"[#7F848E]○ No match [{timestamp_str}] "
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

    # Include source statistics in the results
    source_stats = {
        "shazam": len([t for t in track_matches.values() if t.source == "shazam"]),
        "acrcloud": len([t for t in track_matches.values() if t.source == "acrcloud"]),
    }

    return {
        "full_results": results,
        "tracklist": valid_tracks,
        "total_segments": total_segments,
        "detected_tracks": len(valid_tracks),
        "success_rate": (len(results) / total_segments) * 100
        if total_segments > 0
        else 0,
        "source_stats": source_stats,
    }
