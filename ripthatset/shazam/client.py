import asyncio
import json
from typing import Optional

import aiohttp
from rich.console import Console
from shazamio import Shazam

from ..config import ShazamConfig

console = Console()


class FastShazam:
    def __init__(self, config: ShazamConfig):
        self._shazam = Shazam()
        self._config = config
        self._session = None
        self._retries = {}  # Track retries per segment

    async def recognize(
        self, audio_bytes: bytes, segment_id: Optional[int] = None
    ) -> Optional[dict]:
        """
        Recognize audio using Shazam API with retry logic and detailed error reporting.

        Args:
            audio_bytes: Raw audio data to analyze
            segment_id: Optional segment identifier for tracking retries

        Returns:
            Recognition results or None if recognition failed
        """
        retry_count = 0
        segment_str = (
            f"segment {segment_id}" if segment_id is not None else "current segment"
        )

        while retry_count < self._config.max_retries:
            try:
                result = await self._shazam.recognize(
                    audio_bytes, proxy=self._config.proxy
                )
                # Reset retry count on success
                if segment_id is not None:
                    self._retries[segment_id] = 0
                return result

            except (aiohttp.ClientError, json.JSONDecodeError) as e:
                retry_count += 1
                if segment_id is not None:
                    self._retries[segment_id] = retry_count

                if retry_count < self._config.max_retries:
                    if "407" in str(e):
                        return await self._handle_proxy_error(retry_count, segment_str)
                    elif isinstance(e, aiohttp.ClientError):
                        return await self._handle_connection_error(
                            e, retry_count, segment_str
                        )
                    else:
                        return await self._handle_json_error(
                            e, retry_count, segment_str
                        )
                else:
                    console.print(
                        f"[red]Max retries reached for {segment_str}: {str(e)}[/red]"
                    )
                    return None

            except Exception as e:
                retry_count += 1
                if retry_count < self._config.max_retries:
                    console.print(
                        f"[yellow]Recognition error for {segment_str}, "
                        f"retrying ({retry_count}/{self._config.max_retries}): "
                        f"{str(e)}[/yellow]"
                    )
                    await asyncio.sleep(
                        self._config.retry_delay * retry_count
                    )  # Exponential backoff
                else:
                    console.print(
                        f"[red]Max retries reached for {segment_str}: {str(e)}[/red]"
                    )
                    return None

    async def _handle_proxy_error(self, retry_count: int, segment_str: str) -> None:
        """Handle proxy authentication errors."""
        console.print(
            f"[#E5C07B]⚠ Proxy authentication error for {segment_str}, "
            f"retrying ({retry_count}/{self._config.max_retries})[/#E5C07B]",
            highlight=False,
        )
        await asyncio.sleep(self._config.retry_delay)
        return None

    async def _handle_connection_error(
        self, error: Exception, retry_count: int, segment_str: str
    ) -> None:
        """Handle connection-related errors."""
        console.print(
            f"[#E5C07B]⚠ Connection error for {segment_str}, "
            f"retrying ({retry_count}/{self._config.max_retries}): "
            f"{str(error)}[/#E5C07B]",
            highlight=False,
        )
        await asyncio.sleep(self._config.retry_delay * retry_count)
        return None

    async def _handle_json_error(
        self, error: Exception, retry_count: int, segment_str: str
    ) -> None:
        """Handle JSON decoding errors."""
        console.print(
            f"[#E5C07B]⚠ JSON decode error for {segment_str}, "
            f"retrying ({retry_count}/{self._config.max_retries})[/#E5C07B]",
            highlight=False,
        )
        await asyncio.sleep(self._config.retry_delay)
        return None

    async def close(self):
        """Clean up resources."""
        if self._session and not self._session.closed:
            self._session.close()

    def get_retry_stats(self) -> dict:
        """Get statistics about retries."""
        if not self._retries:
            return {"max_retries": 0, "avg_retries": 0, "total_retries": 0}

        retries = list(self._retries.values())
        return {
            "max_retries": max(retries),
            "avg_retries": sum(retries) / len(retries),
            "total_retries": sum(retries),
        }
