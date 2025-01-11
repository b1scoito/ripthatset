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
    source: str = "shazam"  # Track which service found this match
    segments: List[int] = field(default_factory=list)
    total_matches: int = 0
    clusters: List[List[int]] = field(default_factory=list)
    last_valid_segment: int = 0  # Track last valid segment for better transitions

    def add_segment(self, segment_number: int) -> None:
        """Add a segment and update clusters."""
        if segment_number not in self.segments:
            self.segments.append(segment_number)
            self.total_matches += 1
            self.segments.sort()
            if self._is_segment_valid(segment_number):
                self.last_valid_segment = segment_number
            self._update_clusters()

    def _is_segment_valid(self, segment_number: int) -> bool:
        """Check if a segment is valid based on context."""
        # Verify segment is not an outlier by checking nearby matches
        nearby_matches = sum(1 for s in self.segments if abs(s - segment_number) <= 3)
        return nearby_matches >= 2

    def _update_clusters(self) -> None:
        """Group segments into clusters based on configuration."""
        clusters = []
        current_cluster = []

        # Use dynamic gap threshold based on track length
        max_gap = min(self.config.max_segment_gap, max(2, len(self.segments) // 10))

        for segment in self.segments:
            if not current_cluster:
                current_cluster = [segment]
            else:
                # Check proximity to previous segment
                if segment - current_cluster[-1] <= max_gap:
                    # Verify segment continuity
                    if self._is_segment_valid(segment):
                        current_cluster.append(segment)
                else:
                    if len(current_cluster) >= self.config.min_cluster_size:
                        clusters.append(current_cluster)
                    current_cluster = [segment]

        # Add final cluster if valid
        if current_cluster and len(current_cluster) >= self.config.min_cluster_size:
            clusters.append(current_cluster)

        self.clusters = clusters

    @property
    def is_valid(self) -> bool:
        """Check if track meets validation criteria."""
        return (
            len(self.segments) >= max(3, self.config.min_segment_matches)
            and self.confidence >= self.config.min_confidence
            and len(self.clusters) > 0
            and self._has_consistent_matches()
        )

    def _has_consistent_matches(self) -> bool:
        """Check if matches are consistently spaced."""
        if len(self.segments) < 3:
            return False

        gaps = [
            self.segments[i + 1] - self.segments[i]
            for i in range(len(self.segments) - 1)
        ]
        avg_gap = sum(gaps) / len(gaps)
        return all(abs(gap - avg_gap) <= 2 for gap in gaps)

    @property
    def strongest_cluster(self) -> Optional[List[int]]:
        """Get the most reliable cluster based on consistency."""
        if not self.clusters:
            return None

        # Prioritize clusters with consistent spacing
        valid_clusters = [c for c in self.clusters if len(c) >= 3]
        if not valid_clusters:
            return None

        return max(
            valid_clusters,
            key=lambda c: (len(c), -sum(c[i + 1] - c[i] for i in range(len(c) - 1))),
        )

    @property
    def verified_timestamp(self) -> int:
        """Get the earliest reliable timestamp."""
        if not self.strongest_cluster:
            return 0
        # Use first consistent segment from strongest cluster
        return self.strongest_cluster[0]

    def to_dict(self) -> dict:
        """Convert track to dictionary format."""
        strongest = self.strongest_cluster or []
        segment_number = min(self.segments) if self.segments else 0

        return {
            "title": self.title,
            "artist": self.artist,
            "track_id": self.track_id,
            "confidence": self.confidence,
            "total_matches": self.total_matches,
            "segments": ", ".join(str(s + 1) for s in self.segments[:5]),
            "segment_number": segment_number,
            "timestamp": segment_number,
            "strongest_cluster": [s + 1 for s in strongest],
            "cluster_count": len(self.clusters),
            "cluster_sizes": [len(c) for c in self.clusters],
            "source": self.source,
            "last_valid": self.last_valid_segment,
        }
