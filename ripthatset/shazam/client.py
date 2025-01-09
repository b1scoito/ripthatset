import asyncio
import json
from typing import Optional

import aiohttp
import typer
from shazamio import Shazam

from ..config import ShazamConfig


class FastShazam:
    def __init__(self, config: ShazamConfig):
        self._shazam = Shazam()
        self._config = config
        self._session = None

    async def recognize(self, audio_bytes: bytes) -> Optional[dict]:
        """
        Recognize audio using Shazam API with retry logic.

        Args:
            audio_bytes: Raw audio data to analyze

        Returns:
            Recognition results or None if recognition failed
        """
        retry_count = 0

        while retry_count < self._config.max_retries:
            try:
                return await self._shazam.recognize(
                    audio_bytes, proxy=self._config.proxy
                )
            except (aiohttp.ClientError, json.JSONDecodeError) as e:
                retry_count += 1
                if retry_count < self._config.max_retries:
                    if "407" in str(e):
                        typer.echo(
                            f"Proxy authentication error, retrying "
                            f"({retry_count}/{self._config.max_retries})..."
                        )
                    else:
                        typer.echo(
                            f"Connection error, retrying "
                            f"({retry_count}/{self._config.max_retries}): {str(e)}"
                        )
                    await asyncio.sleep(self._config.retry_delay)
                else:
                    typer.echo(f"Max retries reached for error: {str(e)}")
                    return None
            except Exception as e:
                retry_count += 1
                if retry_count < self._config.max_retries:
                    typer.echo(
                        f"Recognition error, retrying "
                        f"({retry_count}/{self._config.max_retries}): {str(e)}"
                    )
                    await asyncio.sleep(self._config.retry_delay)
                else:
                    typer.echo(f"Max retries reached for error: {str(e)}")
                    return None

    async def close(self):
        """Clean up resources."""
        if self._session and not self._session.closed:
            self._session.close()
