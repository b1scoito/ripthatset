from dataclasses import dataclass
from time import time
from typing import Dict


@dataclass
class ProgressTracker:
    total: int
    processed: int = 0
    successful: int = 0
    start_time: float = time()

    def update(self, success: bool = True) -> None:
        """Update progress counters."""
        self.processed += 1
        if success:
            self.successful += 1

    def get_stats(self) -> Dict:
        """Get current progress statistics."""
        elapsed = time() - self.start_time
        rate = self.processed / elapsed if elapsed > 0 else 0
        remaining = (self.total - self.processed) / rate if rate > 0 else 0
        success_rate = (self.successful / self.processed * 100) if self.processed > 0 else 0

        return {
            "processed": self.processed,
            "total": self.total,
            "elapsed": elapsed,
            "remaining": remaining,
            "success_rate": success_rate,
            "rate_per_second": rate
        }

    def format_progress(self) -> str:
        """Format current progress as string."""
        stats = self.get_stats()
        return (
            f"Progress: {stats['processed']}/{stats['total']} segments "
            f"({(stats['processed']/stats['total']*100):.1f}%) "
            f"[{stats['elapsed']:.1f}s elapsed, ~{stats['remaining']:.1f}s remaining] "
            f"Success rate: {stats['success_rate']:.1f}%"
        )
