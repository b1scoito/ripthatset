from dataclasses import dataclass
from typing import Optional


@dataclass
class ShazamConfig:
    max_retries: int = 7  # Increased retries
    retry_delay: int = 2  # Increased delay between retries
    proxy: Optional[str] = None


@dataclass
class ACRCloudConfig:
    access_key: str
    access_secret: str
    host: str = "identify-us-west-2.acrcloud.com"
    timeout: int = 15  # Increased timeout
    max_retries: int = 7  # Increased retries
    retry_delay: int = 2  # Increased delay between retries
    proxy: Optional[str] = None


@dataclass
class TrackMatchConfig:
    min_segment_matches: int = 3  # Increased minimum segments
    max_segment_gap: int = 2  # Reduced max gap between segments
    min_cluster_size: int = 3  # Increased minimum cluster size
    min_confidence: float = 0.7  # Increased confidence threshold


@dataclass
class ProcessingConfig:
    segment_length: int = 12000  # Reduced segment length for more granular analysis
    use_acrcloud_fallback: bool = True
    min_gap_segments: int = 3  # Reduced minimum gap segments
    batch_size: Optional[int] = 15  # Smaller batch size for more reliable processing
    cpu_count: Optional[int] = None


@dataclass
class OutputConfig:
    json_file: Optional[str] = None
    verbose: bool = True  # Enabled verbose output by default
    show_gaps: bool = True
    min_gap_duration: int = 20  # Reduced minimum gap duration
