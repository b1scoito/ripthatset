import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.theme import Theme
from typing_extensions import Annotated

from ripthatset.config import (
    OutputConfig,
    ProcessingConfig,
    ShazamConfig,
    TrackMatchConfig,
)
from ripthatset.processor import process_segments
from ripthatset.utils.gaps import find_gaps

# Initialize Rich console with custom theme
console = Console(
    theme=Theme(
        {"info": "cyan", "warning": "yellow", "error": "red", "success": "green"}
    )
)

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
        console.print(f"[error]File {audio_file} does not exist[/error]")
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
                console.print(
                    f"\n[success]Results saved to {output_config.json_file}[/success]"
                )

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

        # Print final tracklist
        console.print("\n[info]Final Tracklist:[/info]")

        # Merge and sort tracks and gaps
        all_tracks = list(results["tracklist"].values()) + gaps
        sorted_tracks = sorted(all_tracks, key=lambda x: x["timestamp"])

        for i, track in enumerate(sorted_tracks, 1):
            minutes = int(track["timestamp"] // 60)
            seconds = int(track["timestamp"] % 60)

            if track.get("is_gap"):
                duration_minutes = int(track["duration"] // 60)
                duration_seconds = int(track["duration"] % 60)
                console.print(
                    f"[warning]{i}. ID - ID "
                    f"({minutes:02d}:{seconds:02d}) "
                    f"[duration: {duration_minutes:02d}:{duration_seconds:02d}][/warning]"
                )
            else:
                console.print(
                    f"[success]{i}. {track['artist']} - {track['title']} "
                    f"({minutes:02d}:{seconds:02d}) "
                    f"[segments: {track['segments']}, "
                    f"confidence: {track['confidence']:.2f}, "
                    f"total matches: {track['total_matches']}][/success]"
                )

        # Print summary
        console.print("\n[info]Analysis Summary:[/info]")
        console.print(f"[info]Total Segments: {results['total_segments']}[/info]")
        console.print(f"[info]Detected Tracks: {results['detected_tracks']}[/info]")
        console.print(f"[info]Success Rate: {results['success_rate']:.1f}%[/info]")

    except Exception as e:
        console.print(f"[error]Error processing file: {str(e)}[/error]")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
