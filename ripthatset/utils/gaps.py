from typing import Dict, List


def find_gaps(
    tracks: Dict,
    total_segments: int,
    segment_length: int,
    min_gap_segments: int = 5,
    min_gap_duration: int = 30
) -> List[Dict]:
    """
    Find significant gaps between detected tracks.

    Args:
        tracks: Dictionary of detected tracks
        total_segments: Total number of segments in audio
        segment_length: Length of each segment in milliseconds
        min_gap_segments: Minimum segments to consider a gap
        min_gap_duration: Minimum gap duration in seconds to include

    Returns:
        List of gap entries with timestamps and durations
    """
    sorted_tracks = sorted(tracks.values(), key=lambda x: x["timestamp"])
    gaps = []
    current_segment = 0

    for track in sorted_tracks:
        track_segment = track["segment_number"]
        gap_size = track_segment - current_segment

        if gap_size >= min_gap_segments:
            gap_start = current_segment * (segment_length / 1000)
            gap_end = track_segment * (segment_length / 1000)
            gap_duration = gap_end - gap_start

            if gap_duration >= min_gap_duration:
                gaps.append({
                    "title": "ID",
                    "artist": "ID",
                    "timestamp": gap_start,
                    "end_timestamp": gap_end,
                    "segment_number": current_segment,
                    "is_gap": True,
                    "duration": gap_duration,
                })

        # Update current position based on track's last detected segment
        segments = [int(s)-1 for s in track["segments"].split(", ")]
        current_segment = max(segments) + 1 if segments else track_segment + 1

    # Check for gap at the end
    final_gap_size = total_segments - current_segment
    if final_gap_size >= min_gap_segments:
        gap_start = current_segment * (segment_length / 1000)
        gap_end = total_segments * (segment_length / 1000)
        gap_duration = gap_end - gap_start

        if gap_duration >= min_gap_duration:
            gaps.append({
                "title": "ID",
                "artist": "ID",
                "timestamp": gap_start,
                "end_timestamp": gap_end,
                "segment_number": current_segment,
                "is_gap": True,
                "duration": gap_duration,
            })

    return gaps
