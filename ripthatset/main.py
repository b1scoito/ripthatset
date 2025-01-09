import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

from ripthatset.config import (
    OutputConfig,
    ProcessingConfig,
    ShazamConfig,
    TrackMatchConfig,
)
from ripthatset.processor import process_segments
from ripthatset.utils.gaps import find_gaps

app = typer.Typer()


@app.command()
def recognize(
    audio_file: Annotated[Path, typer.Argument(help="Audio file to analyze")],
    segment_length: Annotated[
        int, typer.Option(help="Segment length in milliseconds")
    ] = 12000,
    proxy: Annotated[Optional[str], typer.Option(help="HTTP/HTTPS proxy URL")] = None,
    json_output: Annotated[
        Optional[Path], typer.Option(help="Save results to JSON file")
    ] = None,
    min_matches: Annotated[
        int, typer.Option(help="Minimum segment matches required")
    ] = 2,
    min_confidence: Annotated[
        float, typer.Option(help="Minimum confidence score (0-1)")
    ] = 0.5,
    max_gap: Annotated[int, typer.Option(help="Maximum segment gap in cluster")] = 3,
    min_cluster: Annotated[int, typer.Option(help="Minimum segments in cluster")] = 2,
    show_gaps: Annotated[bool, typer.Option(help="Show unidentified gaps")] = True,
    min_gap_duration: Annotated[
        int, typer.Option(help="Minimum gap duration (seconds)")
    ] = 30,
    verbose: Annotated[bool, typer.Option(help="Enable verbose output")] = False,
    cpu_count: Annotated[
        Optional[int], typer.Option(help="Number of CPU cores to use")
    ] = None,
):
    """
    Recognize songs in an audio file using Shazam API with customizable parameters.
    """
    if not audio_file.exists():
        typer.echo(f"File {audio_file} does not exist")
        raise typer.Exit(1)

    # Create configurations
    shazam_config = ShazamConfig(proxy=proxy)
    track_config = TrackMatchConfig(
        min_segment_matches=min_matches,
        max_segment_gap=max_gap,
        min_cluster_size=min_cluster,
        min_confidence=min_confidence,
    )
    process_config = ProcessingConfig(
        segment_length=segment_length, cpu_count=cpu_count
    )
    output_config = OutputConfig(
        json_file=str(json_output) if json_output else None,
        verbose=verbose,
        show_gaps=show_gaps,
        min_gap_duration=min_gap_duration,
    )

    try:
        # Process audio file
        results = asyncio.run(
            process_segments(audio_file, shazam_config, track_config, process_config)
        )

        # Save JSON output if requested
        if output_config.json_file:
            with open(output_config.json_file, "w") as f:
                json.dump(results["tracklist"], f, indent=2)
                typer.echo(f"\nResults saved to {output_config.json_file}")

        # Find gaps if enabled
        if output_config.show_gaps:
            gaps = find_gaps(
                results["tracklist"],
                results["total_segments"],
                process_config.segment_length,
                min_gap_duration=output_config.min_gap_duration,
            )
        else:
            gaps = []

        # Output formatted tracklist
        print_tracklist(results["tracklist"], gaps, output_config)

        # Print statistics
        print_statistics(results["stats"])

    except Exception as e:
        typer.echo(f"Error processing file: {str(e)}")
        raise typer.Exit(1)


def print_tracklist(tracklist: dict, gaps: list, config: OutputConfig) -> None:
    """Print formatted tracklist with optional gaps."""
    typer.echo("\nFinal Tracklist:")

    try:
        # Merge tracks and gaps and sort by timestamp
        all_tracks = list(tracklist.values()) + gaps
        sorted_tracks = sorted(all_tracks, key=lambda x: x["timestamp"])

        for i, track in enumerate(sorted_tracks, 1):
            timestamp = track["timestamp"]  # timestamp is now in seconds
            minutes = int(timestamp // 60)
            seconds = int(timestamp % 60)

            if track.get("is_gap"):
                duration_minutes = int(track["duration"] // 60)
                duration_seconds = int(track["duration"] % 60)
                typer.echo(
                    f"{i}. ID - ID "
                    f"({minutes:02d}:{seconds:02d}) "
                    f"[duration: {duration_minutes:02d}:{duration_seconds:02d}]"
                )
            else:
                typer.echo(
                    f"{i}. {track['artist']} - {track['title']} "
                    f"({minutes:02d}:{seconds:02d}) "
                    f"[segments: {track['segments']}, "
                    f"confidence: {track['confidence']:.2f}, "
                    f"total matches: {track['total_matches']}]"
                )

                if config.verbose:
                    typer.echo(f"   Clusters: {track['cluster_sizes']}")
    except Exception as e:
        typer.echo(f"Error printing tracklist: {str(e)}")
        # Continue execution even if printing fails


def print_statistics(stats: dict) -> None:
    """Print processing statistics."""
    typer.echo(f"\nProcessing completed in {stats['elapsed']:.1f} seconds")
    typer.echo(f"Success rate: {stats['success_rate']:.1f}%")


if __name__ == "__main__":
    app()
