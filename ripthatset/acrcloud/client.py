import asyncio
import base64
import hashlib
import hmac
import json
import time
from typing import Dict, Optional

import aiohttp
from rich.console import Console

from ..config import ACRCloudConfig

console = Console()


class ACRCloudClient:
    def __init__(self, config: ACRCloudConfig):
        self._access_key = config.access_key
        self._access_secret = (
            config.access_secret.encode("ascii")
            if not isinstance(config.access_secret, bytes)
            else config.access_secret
        )
        self._config = config
        self._host = config.host
        self._endpoint = f"https://{config.host}/v1/identify"
        self._timeout = aiohttp.ClientTimeout(total=config.timeout, connect=30)
        self._session: Optional[aiohttp.ClientSession] = None
        self._retries = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    def _sign_string(self, string_to_sign: str) -> str:
        """Sign a string using HMAC-SHA1."""
        hmac_obj = hmac.new(
            self._access_secret, string_to_sign.encode("ascii"), hashlib.sha1
        )
        return base64.b64encode(hmac_obj.digest()).decode("ascii")

    def _prepare_request_data(self, audio_data: bytes) -> Dict:
        """Prepare request data for ACRCloud API."""
        timestamp = time.time()
        string_to_sign = "\n".join(
            [
                "POST",
                "/v1/identify",
                self._access_key,
                "audio",
                "1",
                str(timestamp),
            ]
        )

        signature = self._sign_string(string_to_sign)

        data = {
            "access_key": self._access_key,
            "sample_bytes": len(audio_data),
            "timestamp": str(timestamp),
            "signature": signature,
            "data_type": "audio",
            "signature_version": "1",
        }

        return {
            "data": data,
            "files": [("sample", ("test.mp3", audio_data, "audio/mpeg"))],
        }

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

    async def recognize(
        self, audio_data: bytes, segment_id: Optional[int] = None
    ) -> Optional[Dict]:
        """Recognize audio using ACRCloud API."""
        retry_count = 0
        segment_str = (
            f"segment {segment_id}" if segment_id is not None else "current segment"
        )

        while retry_count < self._config.max_retries:
            try:
                session = await self._get_session()
                request_data = self._prepare_request_data(audio_data)

                form = aiohttp.FormData()
                for key, value in request_data["data"].items():
                    form.add_field(key, str(value))
                file_info = request_data["files"][0]
                form.add_field(
                    file_info[0],
                    file_info[1][1],
                    filename=file_info[1][0],
                    content_type=file_info[1][2],
                )

                try:
                    proxy = (
                        None
                        if retry_count == self._config.max_retries - 1
                        else self._config.proxy
                    )
                    async with session.post(
                        self._endpoint, data=form, proxy=proxy
                    ) as response:
                        text_response = await response.text()

                        if response.status != 200:
                            retry_count += 1
                            if retry_count < self._config.max_retries:
                                console.print(
                                    f"[#E5C07B]ACRCloud API error: {response.status}, retrying...[/#E5C07B]",
                                    highlight=False,
                                )
                                await asyncio.sleep(
                                    self._config.retry_delay * retry_count
                                )
                                continue
                            return None

                        result = json.loads(text_response)

                except (asyncio.TimeoutError, TimeoutError):
                    retry_count += 1
                    if retry_count < self._config.max_retries:
                        console.print(
                            f"[#E5C07B]⚠ Timeout error for {segment_str}, "
                            f"retrying ({retry_count}/{self._config.max_retries})[/#E5C07B]",
                            highlight=False,
                        )
                        await asyncio.sleep(self._config.retry_delay * retry_count)
                        continue
                    return None

                if result["status"]["code"] != 0:
                    if result["status"]["code"] == 3001:
                        console.print(
                            "[#E5C07B]Invalid access key. Please check your ACRCloud credentials.[/#E5C07B]",
                            highlight=False,
                        )
                    elif result["status"]["code"] != 1001:  # Ignore "No result"
                        console.print(
                            f"[#7F848E]ACRCloud status: {result['status']['msg']}[/#7F848E]",
                            highlight=False,
                        )
                    return None

                if result.get("metadata", {}).get("music"):
                    music = result["metadata"]["music"][0]
                    if segment_id is not None:
                        self._retries[segment_id] = retry_count

                    return {
                        "matches": [
                            {"score": min(float(music.get("score", 100)), 100)}
                        ],
                        "track": {
                            "key": music.get("external_ids", {}).get("isrc", ""),
                            "title": music.get("title", ""),
                            "subtitle": music.get("artists", [{}])[0].get("name", ""),
                            "release_date": music.get("release_date", ""),
                            "album": {"name": music.get("album", {}).get("name", "")},
                            "artists": [
                                {"name": artist.get("name", "")}
                                for artist in music.get("artists", [])
                            ],
                            "genres": [
                                {"name": genre.get("name", "")}
                                for genre in music.get("genres", [])
                            ],
                            "external_ids": music.get("external_ids", {}),
                            "external_metadata": music.get("external_metadata", {}),
                        },
                    }

                return None

            except aiohttp.ClientError as e:
                retry_count += 1
                if retry_count < self._config.max_retries:
                    if "407" in str(e):
                        await self._handle_proxy_error(retry_count, segment_str)
                    else:
                        await self._handle_connection_error(e, retry_count, segment_str)
                    continue
                return None

            except json.JSONDecodeError as e:
                retry_count += 1
                if retry_count < self._config.max_retries:
                    await self._handle_json_error(e, retry_count, segment_str)
                    continue
                return None

            except Exception as e:
                console.print(
                    f"[#E5C07B]ACRCloud error: {str(e)}[/#E5C07B]", highlight=False
                )
                import traceback

                console.print(
                    f"[#E5C07B]Full error: {traceback.format_exc()}[/#E5C07B]"
                )
                return None

    async def close(self) -> None:
        """Close the client's resources."""
        if self._session:
            await self._session.close()
            self._session = None

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
