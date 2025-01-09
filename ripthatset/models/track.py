from dataclasses import dataclass, field
from typing import List, Optional

from ..config import TrackMatchConfig


@dataclass
class TrackMatch:
    track_id: str
    title: str
    artist: str
    confidence: float
    config: TrackMatchConfig
    segments: List[int] = field(default_factory=list)
    total_matches: int = 0
    clusters: List[List[int]] = field(default_factory=list)

    def add_segment(self, segment_number: int) -> None:
        """Add a segment and update clusters."""
        if segment_number not in self.segments:
            self.segments.append(segment_number)
            self.total_matches += 1
            self.segments.sort()
            self._update_clusters()

    def _update_clusters(self) -> None:
        """Group segments into clusters based on configuration."""
        clusters = []
        current_cluster = []

        for segment in self.segments:
            if not current_cluster:
                current_cluster = [segment]
            else:
                # Check if segment is within configured gap distance
                if segment - current_cluster[-1] <= self.config.max_segment_gap:
                    current_cluster.append(segment)
                else:
                    # Start new cluster if gap is too large
                    if len(current_cluster) >= self.config.min_cluster_size:
                        clusters.append(current_cluster)
                    current_cluster = [segment]

        # Add the last cluster if it meets size requirement
        if current_cluster and len(current_cluster) >= self.config.min_cluster_size:
            clusters.append(current_cluster)

        self.clusters = clusters

    @property
    def is_valid(self) -> bool:
        """Check if track meets validation criteria."""
        return (
            len(self.segments) >= self.config.min_segment_matches
            and self.confidence >= self.config.min_confidence
            and len(self.clusters) > 0
        )

    @property
    def strongest_cluster(self) -> Optional[List[int]]:
        """Get the cluster with the most segments."""
        if not self.clusters:
            return None
        return max(self.clusters, key=len)

    @property
    def verified_timestamp(self) -> int:
        """Get the earliest timestamp from the strongest cluster."""
        if not self.strongest_cluster:
            return 0
        return min(self.strongest_cluster)

    def to_dict(self) -> dict:
        """Convert track to dictionary format."""
        strongest = self.strongest_cluster or []
        segment_number = (
            min(self.segments) if self.segments else 0
        )  # Get earliest segment

        return {
            "title": self.title,
            "artist": self.artist,
            "track_id": self.track_id,
            "confidence": self.confidence,
            "total_matches": self.total_matches,
            "segments": ", ".join(str(s + 1) for s in self.segments[:5]),
            "segment_number": segment_number,
            "timestamp": segment_number,  # Add timestamp based on first segment
            "strongest_cluster": [s + 1 for s in strongest],
            "cluster_count": len(self.clusters),
            "cluster_sizes": [len(c) for c in self.clusters],
        }
