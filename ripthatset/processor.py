import asyncio
import tempfile
import time
from pathlib import Path
from typing import Dict

import typer

from ripthatset.config import ProcessingConfig, ShazamConfig, TrackMatchConfig
from ripthatset.models import ProgressTracker, TrackMatch
from ripthatset.shazam import FastShazam
from ripthatset.utils import calculate_optimal_batch_size, split_audio


async def recognize_segment(
    shazam: FastShazam,
    segment_path: Path,
    segment_number: int,
    segment_length: int,
) -> Dict:
    """Process a single audio segment."""
    try:
        start_time = time.time()
        typer.echo(f"Analyzing segment {segment_number + 1}...")

        with open(segment_path, "rb") as f:
            audio_bytes = f.read()

        result = await shazam.recognize(audio_bytes)
        end_time = time.time()
        elapsed = end_time - start_time

        if result and isinstance(result, dict):
            if result.get("matches"):
                track = result["track"]
                timestamp = segment_number * (segment_length / 1000)
                minutes = int(timestamp // 60)
                seconds = int(timestamp % 60)
                typer.echo(
                    f"Found: {track['subtitle']} - {track['title']} "
                    f"({minutes:02d}:{seconds:02d}) [took {elapsed:.2f}s]"
                )
                result["segment_number"] = segment_number
                result["timestamp"] = timestamp
                return result
            else:
                typer.echo(f"No match found [took {elapsed:.2f}s]")
        return None

    except Exception as e:
        typer.echo(f"Error recognizing segment {segment_number + 1}: {str(e)}")
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
    track_matches = {}  # track_id -> TrackMatch
    segment_length = process_config.segment_length  # Store for timestamp calculations

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Split audio into segments
        typer.echo("Splitting audio file into segments using FFmpeg...")
        segment_files = split_audio(
            audio_path,
            temp_path,
            segment_length / 1000,  # Convert to seconds
        )

        total_segments = len(segment_files)
        batch_size = process_config.batch_size or calculate_optimal_batch_size(
            total_segments, process_config.cpu_count
        )
        progress = ProgressTracker(total_segments)

        typer.echo(
            f"Processing {total_segments} segments in batches of {batch_size}..."
        )

        # Process segments in batches
        for i in range(0, len(segment_files), batch_size):
            batch = segment_files[i : i + batch_size]
            tasks = []

            for j, segment_path in enumerate(batch):
                segment_number = i + j
                tasks.append(
                    recognize_segment(
                        shazam, segment_path, segment_number, segment_length
                    )
                )

            # Process batch results
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for j, result in enumerate(batch_results):
                segment_number = i + j

                if isinstance(result, dict) and result.get("matches"):
                    results[segment_number] = result
                    track = result["track"]
                    track_id = track["key"]
                    confidence = result.get("matches", [{}])[0].get("score", 100) / 100

                    if track_id not in track_matches:
                        track_matches[track_id] = TrackMatch(
                            track_id=track_id,
                            title=track["title"],
                            artist=track["subtitle"],
                            confidence=confidence,
                            config=track_config,
                        )

                    track_matches[track_id].add_segment(segment_number)
                    progress.update(True)
                else:
                    progress.update(False)

                # Print progress
                typer.echo(progress.format_progress())

            # Add small delay between batches
            await asyncio.sleep(1)

        # Create tracklist from valid matches and calculate real timestamps
        valid_tracks = {}
        for track_id, match in track_matches.items():
            if match.is_valid:
                track_dict = match.to_dict()
                # Convert segment number to real timestamp (segment_length is in milliseconds)
                segment_seconds = segment_length / 1000  # Convert to seconds
                track_dict["timestamp"] = track_dict["segment_number"] * segment_seconds
                valid_tracks[track_id] = track_dict

        await shazam.close()

    return {
        "full_results": results,
        "tracklist": valid_tracks,
        "stats": progress.get_stats(),
        "total_segments": total_segments,
    }
