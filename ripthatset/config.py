from dataclasses import dataclass
from typing import Optional


@dataclass
class ShazamConfig:
    max_retries: int = 5
    retry_delay: int = 1
    proxy: Optional[str] = None

@dataclass
class TrackMatchConfig:
    min_segment_matches: int = 2  # Minimum segments to consider a valid track
    max_segment_gap: int = 3      # Maximum gap between segments in a cluster
    min_cluster_size: int = 2     # Minimum segments in a cluster
    min_confidence: float = 0.5   # Minimum confidence score to accept

@dataclass
class ProcessingConfig:
    segment_length: int = 12000   # Length of each segment in milliseconds
    min_gap_segments: int = 5     # Minimum segments to consider a gap
    batch_size: Optional[int] = None  # If None, will be calculated automatically
    cpu_count: Optional[int] = None   # If None, will use system CPU count

@dataclass
class OutputConfig:
    json_file: Optional[str] = None    # JSON output file path
    verbose: bool = False              # Enable verbose output
    show_gaps: bool = True            # Show gaps in tracklist
    min_gap_duration: int = 30        # Minimum gap duration in seconds to show
