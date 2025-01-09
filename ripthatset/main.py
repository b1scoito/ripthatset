import asyncio
import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp
import typer
from shazamio import Shazam

app = typer.Typer()


@dataclass
class TrackMatch:
    def __init__(self, track_id: str, title: str, artist: str, confidence: float):
        self.track_id = track_id
        self.title = title
        self.artist = artist
        self.confidence = confidence
        self.segments = []
        self.total_matches = 0
        self.clusters = []  # Will hold groups of consecutive segments

    def add_segment(self, segment_number: int):
        if segment_number not in self.segments:
            self.segments.append(segment_number)
            self.total_matches += 1
            self.segments.sort()
            self._update_clusters()

    def _update_clusters(self):
        """Group segments into clusters of consecutive or near-consecutive matches"""
        clusters = []
        current_cluster = []

        for i, segment in enumerate(self.segments):
            if not current_cluster:
                current_cluster = [segment]
            else:
                # If this segment is close to the last one in current cluster
                if segment - current_cluster[-1] <= 3:  # Allow 3 segment gaps
                    current_cluster.append(segment)
                else:
                    # Start new cluster if gap is too large
                    if (
                        len(current_cluster) >= 2
                    ):  # Only keep clusters with at least 2 segments
                        clusters.append(current_cluster)
                    current_cluster = [segment]

        # Add the last cluster if it exists and has enough segments
        if current_cluster and len(current_cluster) >= 2:
            clusters.append(current_cluster)

        self.clusters = clusters

    @property
    def is_valid(self) -> bool:
        # Track must have at least one valid cluster
        return len(self.clusters) > 0

    @property
    def strongest_cluster(self):
        """Return the cluster with the most segments"""
        if not self.clusters:
            return None
        return max(self.clusters, key=len)

    @property
    def verified_timestamp(self) -> int:
        """Return the timestamp based on the start of the strongest cluster"""
        if not self.strongest_cluster:
            return 0
        return min(
            self.strongest_cluster
        )  # Return earliest segment in strongest cluster


@dataclass
class ProgressTracker:
    total: int
    processed: int = 0
    successful: int = 0
    start_time: float = time.time()

    def update(self, success: bool = True):
        self.processed += 1
        if success:
            self.successful += 1

    def get_stats(self) -> Dict:
        elapsed = time.time() - self.start_time
        rate = self.processed / elapsed if elapsed > 0 else 0
        remaining = (self.total - self.processed) / rate if rate > 0 else 0
        success_rate = (
            (self.successful / self.processed * 100) if self.processed > 0 else 0
        )

        return {
            "processed": self.processed,
            "total": self.total,
            "elapsed": elapsed,
            "remaining": remaining,
            "success_rate": success_rate,
        }


class FastShazam:
    def __init__(self, proxy: Optional[str] = None):
        self._shazam = Shazam()
        self._proxy = proxy

    async def recognize(self, audio_bytes: bytes) -> Optional[dict]:
        max_retries = 5
        retry_count = 0

        while retry_count < max_retries:
            try:
                return await self._shazam.recognize(audio_bytes, proxy=self._proxy)
            except (aiohttp.ClientError, json.JSONDecodeError) as e:
                retry_count += 1
                if retry_count < max_retries:
                    if "407" in str(e):
                        typer.echo(
                            f"Proxy authentication error, retrying ({retry_count}/{max_retries})..."
                        )
                    else:
                        typer.echo(
                            f"Connection error, retrying ({retry_count}/{max_retries}): {str(e)}"
                        )
                    await asyncio.sleep(1)
                else:
                    typer.echo(f"Max retries reached for error: {str(e)}")
                    return None
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    typer.echo(
                        f"Recognition error, retrying ({retry_count}/{max_retries}): {str(e)}"
                    )
                    await asyncio.sleep(1)
                else:
                    typer.echo(f"Max retries reached for error: {str(e)}")
                    return None


async def recognize_segment(
    shazam: FastShazam,
    segment_path: Path,
    segment_number: int,
    segment_length: int,
) -> Optional[dict]:
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


def calculate_optimal_batch_size(total_segments: int, cpu_count: int = 4) -> int:
    """
    Calculate optimal batch size based on total segments and system resources.

    Strategy:
    1. For very small sets (<100 segments), use smaller batches
    2. For medium sets, scale with CPU count
    3. For large sets, cap the batch size to avoid overwhelming the system
    4. Never exceed 50 concurrent requests
    """
    if cpu_count is None:
        cpu_count = os.cpu_count() or 2

    # Base calculation
    if total_segments < 100:
        # For small sets, use smaller batches
        base_size = min(10, max(5, total_segments // 10))
    elif total_segments < 500:
        # For medium sets, scale with CPU
        base_size = min(20, max(10, cpu_count * 3))
    else:
        # For large sets, be more conservative
        base_size = min(30, max(15, cpu_count * 2))

    # Adjust based on total segments to CPU ratio
    segments_per_cpu = total_segments / cpu_count
    if segments_per_cpu > 100:
        # For very high segment-to-CPU ratios, increase batch size
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


def find_gaps(
    tracks: Dict, total_segments: int, segment_length: int, min_gap_segments: int = 5
) -> List[Dict]:
    """Find significant gaps between detected tracks and create placeholder entries."""
    # Sort tracks by timestamp
    sorted_tracks = sorted(tracks.values(), key=lambda x: x["timestamp"])

    # Initialize gaps list
    gaps = []
    current_segment = 0

    for track in sorted_tracks:
        track_segment = track["segment_number"]

        # Check if there's a significant gap before this track
        gap_size = track_segment - current_segment
        if gap_size >= min_gap_segments:
            gap_start = current_segment * (segment_length / 1000)
            gap_end = track_segment * (segment_length / 1000)
            gaps.append(
                {
                    "title": "ID",
                    "artist": "ID",
                    "timestamp": gap_start,
                    "end_timestamp": gap_end,
                    "segment_number": current_segment,
                    "is_gap": True,
                    "duration": gap_end - gap_start,
                }
            )

        # Update current_segment to end of this track's match region
        # We'll consider the track spans its detected segments
        segments = [int(s) - 1 for s in track["segments"].split(", ")]
        current_segment = max(segments) + 1 if segments else track_segment + 1

    # Check for gap at the end
    final_gap_size = total_segments - current_segment
    if final_gap_size >= min_gap_segments:
        gap_start = current_segment * (segment_length / 1000)
        gap_end = total_segments * (segment_length / 1000)
        gaps.append(
            {
                "title": "ID",
                "artist": "ID",
                "timestamp": gap_start,
                "end_timestamp": gap_end,
                "segment_number": current_segment,
                "is_gap": True,
                "duration": gap_end - gap_start,
            }
        )

    return gaps


async def process_segments(
    audio_path: Path, segment_length: int = 12000, proxy: Optional[str] = None
) -> Dict:
    shazam = FastShazam(proxy=proxy)
    results = {}
    track_matches = {}  # track_id -> TrackMatch
    batch_size = 20  # Process 20 segments at a time

    with tempfile.TemporaryDirectory() as temp_dir:
        duration_ms = segment_length / 1000
        segment_pattern = os.path.join(temp_dir, "segment_%d.mp3")

        typer.echo("Splitting audio file into segments using FFmpeg...")
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(audio_path),
                "-f",
                "segment",
                "-segment_time",
                str(duration_ms),
                "-acodec",
                "copy",
                segment_pattern,
                "-loglevel",
                "quiet",
            ]
        )

        segment_files = sorted(Path(temp_dir).glob("segment_*.mp3"))
        total_segments = len(segment_files)
        batch_size = calculate_optimal_batch_size(total_segments)
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
                        )

                    track_matches[track_id].add_segment(segment_number)
                    progress.update(True)
                else:
                    progress.update(False)

                # Print progress
                stats = progress.get_stats()
                typer.echo(
                    f"Progress: {stats['processed']}/{stats['total']} segments "
                    f"({(stats['processed']/stats['total']*100):.1f}%) "
                    f"[{stats['elapsed']:.1f}s elapsed, ~{stats['remaining']:.1f}s remaining] "
                    f"Success rate: {stats['success_rate']:.1f}%"
                )

            # Add small delay between batches
            await asyncio.sleep(1)

        # Create valid tracklist with verified timestamps
        valid_tracks = {}
        for track_id, match in track_matches.items():
            if match.is_valid:
                verified_segment = match.verified_timestamp
                first_timestamp = verified_segment * (segment_length / 1000)

                # Get the segments from the strongest cluster
                strongest_cluster = match.strongest_cluster
                cluster_segments_str = ", ".join(
                    str(s + 1) for s in strongest_cluster[:5]
                )

                valid_tracks[track_id] = {
                    "title": match.title,
                    "artist": match.artist,
                    "timestamp": first_timestamp,
                    "segment_number": verified_segment,
                    "confidence": match.confidence,
                    "total_matches": match.total_matches,
                    "segments": cluster_segments_str,
                    "cluster_size": len(strongest_cluster),
                }

    return {
        "full_results": results,
        "tracklist": valid_tracks,
        "stats": progress.get_stats(),
        "total_segments": total_segments,
    }


@app.command()
def recognize(
    audio_file: Path,
    segment_length: int = typer.Option(
        12000, help="Length of each segment in milliseconds (default: 12 seconds)"
    ),
    proxy: Optional[str] = typer.Option(
        None, help="HTTP/HTTPS proxy URL (e.g. http://proxy.example.com:8080)"
    ),
):
    """
    Recognize songs in an audio file using Shazam API
    """
    if not audio_file.exists():
        typer.echo(f"File {audio_file} does not exist")
        raise typer.Exit(1)

    try:
        results = asyncio.run(process_segments(audio_file, segment_length, proxy))
        tracklist = results["tracklist"]

        # Output JSON tracklist
        typer.echo("\nTracklist JSON:")
        typer.echo(json.dumps(tracklist, indent=2))

        # Find gaps between tracks
        gaps = find_gaps(tracklist, results["total_segments"], segment_length)

        # Merge tracks and gaps and sort by timestamp
        all_tracks = list(tracklist.values()) + gaps
        sorted_tracks = sorted(all_tracks, key=lambda x: x["timestamp"])

        # Output formatted tracklist
        typer.echo("\nFinal Tracklist:")
        for i, track in enumerate(sorted_tracks, 1):
            minutes = int(track["timestamp"] // 60)
            seconds = int(track["timestamp"] % 60)

            if track.get("is_gap"):
                # Format gap entry
                duration_minutes = int(track["duration"] // 60)
                duration_seconds = int(track["duration"] % 60)
                typer.echo(
                    f"{i}. {track['artist']} - {track['title']} "
                    f"({minutes:02d}:{seconds:02d}) "
                    f"[duration: {duration_minutes:02d}:{duration_seconds:02d}]"
                )
            else:
                # Format regular track entry
                typer.echo(
                    f"{i}. {track['artist']} - {track['title']} "
                    f"({minutes:02d}:{seconds:02d}) "
                    f"[segments: {track['segments']}, "
                    f"confidence: {track['confidence']:.2f}, "
                    f"total matches: {track['total_matches']}]"
                )

        # Output final statistics
        stats = results["stats"]
        typer.echo(f"\nProcessing completed in {stats['elapsed']:.1f} seconds")
        typer.echo(f"Success rate: {stats['success_rate']:.1f}%")

    except Exception as e:
        typer.echo(f"Error processing file: {str(e)}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
