"""Meta (Instagram) Graph API — direct reel + carousel publishing."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from src.config import AppConfig
from src.pipeline.logger import PipelineLogger
from src.script_gen.post_details import PostDetails
from src.visuals.bgm_audio import probe_audio_codec


@dataclass
class MetaPostResult:
    reel_container_id: str
    reel_publish_id: str | None
    carousel_container_id: str | None
    carousel_publish_id: str | None
    scheduled_reel_at: str
    scheduled_carousel_at: str
    carousel_error: str = ""

    def summary(self) -> str:
        parts = [f"reel:{self.reel_container_id}"]
        if self.reel_publish_id:
            parts.append(f"reel_pub:{self.reel_publish_id}")
        if self.carousel_container_id:
            parts.append(f"carousel:{self.carousel_container_id}")
        if self.carousel_publish_id:
            parts.append(f"carousel_pub:{self.carousel_publish_id}")
        if self.carousel_error:
            parts.append(f"carousel_failed:{self.carousel_error}")
        return ";".join(parts)

    @property
    def reel_posted(self) -> bool:
        return bool(self.reel_publish_id)


class MetaScheduler:
    """Publish reels and carousels via Instagram Graph API."""

    GRAPH_URL = "https://graph.facebook.com/v21.0"
    RUPLOAD_URL = "https://rupload.facebook.com/ig-api-upload/v21.0"
    PHOTO_PERMISSIONS = (
        "pages_manage_posts",
        "pages_read_engagement",
        "pages_show_list",
    )

    POLL_INTERVAL_SEC = 5
    POLL_MAX_ATTEMPTS = 60
    SINGLE_UPLOAD_MAX_BYTES = 50 * 1024 * 1024
    CHUNK_SIZE_BYTES = 4 * 1024 * 1024
    GITHUB_REEL_BRANCH = "ci-reel-uploads"
    GITHUB_REEL_PREFIX = "tmp-ci-reels"
    PUBLISH_RATE_LIMIT_CODES = {4, 17, 32, 613}
    PUBLISH_RATE_LIMIT_SUBCODES = {2207051, 2446079}
    PUBLISH_AMBIGUOUS_SUBCODES = {2207085}  # publish may have succeeded despite HTTP error
    RATE_LIMIT_RETRY_ATTEMPTS = 6
    RATE_LIMIT_RETRY_BASE_SEC = 30
    CAROUSEL_PUBLISH_DELAY_SEC = 240
    CAROUSEL_CHILD_UPLOAD_DELAY_SEC = 2
    PUBLISH_RECOVERY_WINDOW_MIN = 20

    def __init__(self, config: AppConfig, logger: PipelineLogger) -> None:
        self.config = config
        self.logger = logger
        self.ig_user_id = (config.meta_ig_user_id or "").strip()
        self.access_token = (config.meta_access_token or "").strip()
        self.page_id = (config.meta_page_id or "").strip()
        self._pending_github_reel_cleanup: dict[str, str] | None = None

    def is_configured(self) -> bool:
        token = (self.access_token or "").strip()
        return bool(self.ig_user_id and token and token.startswith("EAA"))

    def queue_posts(
        self,
        reel_path: Path,
        static_paths: list[Path] | Path,
        caption: str,
        bundle_id: str,
        *,
        thumbnail_path: Path | None = None,
        post_details: PostDetails | None = None,
    ) -> str:
        if isinstance(static_paths, Path):
            static_paths = [static_paths]

        self.logger.start("meta", bundle_id)

        if not self.is_configured():
            self.logger.warn("meta", "not configured — saving package for manual upload")
            return self._save_manual_package(
                reel_path, static_paths, caption, bundle_id, thumbnail_path
            )

        try:
            return self._queue_posts_configured(
                reel_path,
                static_paths,
                caption,
                bundle_id,
                thumbnail_path=thumbnail_path,
                post_details=post_details,
            )
        except (requests.RequestException, RuntimeError, TimeoutError) as exc:
            self.logger.warn("meta", f"API failed ({exc}) — saving package for manual upload")
            return self._save_manual_package(
                reel_path, static_paths, caption, bundle_id, thumbnail_path
            )

    def _queue_posts_configured(
        self,
        reel_path: Path,
        static_paths: list[Path],
        caption: str,
        bundle_id: str,
        *,
        thumbnail_path: Path | None = None,
        post_details: PostDetails | None = None,
    ) -> str:
        reel_caption = post_details.reel_caption if post_details else caption
        carousel_caption = (
            post_details.carousel_caption if post_details else caption
        )

        reel_time = self._next_post_time()
        carousel_time = reel_time + timedelta(minutes=5)

        cover_url = None
        if thumbnail_path and thumbnail_path.exists():
            cover_url = self._upload_cover_image(thumbnail_path)

        try:
            reel_container = self._create_reel_container(
                self._prepare_reel_for_instagram(reel_path),
                reel_caption,
                cover_url=cover_url,
                publish_at=reel_time,
            )
            reel_publish_id = self._wait_and_publish(reel_container, publish_at=reel_time)
        finally:
            self._cleanup_github_reel_host()

        carousel_container_id = None
        carousel_publish_id = None
        carousel_error = ""
        if static_paths:
            self.logger.info(
                f"meta | waiting {self.CAROUSEL_PUBLISH_DELAY_SEC}s before carousel "
                "(Meta rate-limit cooldown after reel publish)",
            )
            time.sleep(self.CAROUSEL_PUBLISH_DELAY_SEC)
            try:
                carousel_container_id = self._create_carousel_container(
                    static_paths, carousel_caption, publish_at=carousel_time
                )
                carousel_publish_id = self._wait_and_publish(
                    carousel_container_id, publish_at=carousel_time
                )
            except (requests.RequestException, RuntimeError, TimeoutError) as exc:
                carousel_error = self._classify_publish_error(exc)
                self.logger.warn(
                    "meta",
                    f"carousel publish failed after reel posted ({carousel_error}): {exc}",
                )
                self._save_carousel_fallback(
                    static_paths, carousel_caption, bundle_id, carousel_error
                )

        result = MetaPostResult(
            reel_container_id=reel_container,
            reel_publish_id=reel_publish_id,
            carousel_container_id=carousel_container_id,
            carousel_publish_id=carousel_publish_id,
            scheduled_reel_at=reel_time.isoformat(),
            scheduled_carousel_at=carousel_time.isoformat(),
            carousel_error=carousel_error,
        )
        if carousel_error:
            self.logger.warn("meta", f"partial publish — reel ok, carousel failed: {carousel_error}")
        self.logger.ok("meta", result.summary())
        return result.summary()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"OAuth {self.access_token}"}

    def _next_post_time(self) -> datetime:
        tz = ZoneInfo(self.config.timezone)
        now = datetime.now(tz)
        hour, minute = map(int, self.config.post_time.split(":"))
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled <= now:
            scheduled += timedelta(days=1)
        # Meta requires publish_at at least 10 minutes in the future
        min_future = now + timedelta(minutes=11)
        if scheduled < min_future:
            scheduled = min_future
        return scheduled

    def _unix_publish_at(self, when: datetime) -> int:
        return int(when.timestamp())

    def _create_reel_container(
        self,
        video_path: Path,
        caption: str,
        *,
        cover_url: str | None = None,
        publish_at: datetime | None = None,
    ) -> str:
        del publish_at
        self._validate_reel_for_upload(video_path)

        public_url = self._host_reel_publicly(video_path)
        if public_url:
            try:
                return self._create_reel_container_via_video_url(
                    public_url,
                    caption,
                    cover_url=cover_url,
                )
            except (requests.RequestException, RuntimeError) as exc:
                self.logger.warn(
                    "meta",
                    f"video_url reel upload failed ({exc}) — trying rupload binary",
                )

        return self._create_reel_container_via_rupload(
            video_path,
            caption,
            cover_url=cover_url,
        )

    def _create_reel_container_via_video_url(
        self,
        video_url: str,
        caption: str,
        *,
        cover_url: str | None = None,
    ) -> str:
        """Meta fetches the reel from a third-party public URL (bypasses rupload.facebook.com)."""
        use_cover = cover_url
        for attempt in range(2):
            params: dict[str, str] = {
                "access_token": self.access_token,
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption[:2200],
                "share_to_feed": "true",
            }
            if use_cover:
                params["cover_url"] = use_cover

            resp = requests.post(
                f"{self.GRAPH_URL}/{self.ig_user_id}/media",
                params=params,
                timeout=120,
            )
            if resp.status_code >= 400:
                self._log_api_error("reel container video_url", resp)
                if use_cover and attempt == 0:
                    self.logger.warn(
                        "meta",
                        "reel video_url with cover failed — retrying without cover",
                    )
                    use_cover = None
                    continue
                resp.raise_for_status()
            container_id = resp.json()["id"]
            self.logger.info(
                f"Reel container created via video_url: {container_id} ({video_url[:80]})"
            )
            return container_id
        raise RuntimeError("reel video_url container creation failed")

    def _create_reel_container_via_rupload(
        self,
        video_path: Path,
        caption: str,
        *,
        cover_url: str | None = None,
    ) -> str:
        use_cover = cover_url
        container_id: str | None = None
        upload_url: str | None = None
        for attempt in range(2):
            try:
                container_id, upload_url = self._init_reel_upload_session(
                    caption,
                    cover_url=use_cover,
                )
                break
            except (requests.RequestException, RuntimeError) as exc:
                if use_cover and attempt == 0:
                    self.logger.warn(
                        "meta",
                        f"reel container with cover failed ({exc}) — retrying without cover",
                    )
                    use_cover = None
                    continue
                raise
        if not container_id or not upload_url:
            raise RuntimeError("reel container creation failed")

        try:
            self._resumable_upload_binary(
                container_id,
                video_path,
                upload_url=upload_url,
            )
        except (requests.RequestException, RuntimeError) as exc:
            self._log_upload_bytes_transferred(container_id)
            raise RuntimeError(f"reel video upload failed: {exc}") from exc
        return container_id

    def _host_reel_publicly(self, video_path: Path) -> str | None:
        """
        Upload reel bytes to a third-party host so Meta can fetch via video_url.

        Meta-hosted Page video URLs are rejected; external public hosts work.
        rupload.facebook.com binary upload is unreliable on CI and large files.
        """
        import os

        if os.getenv("META_REEL_SKIP_PUBLIC_HOST", "").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            return None

        size = video_path.stat().st_size
        self.logger.info(
            f"meta | hosting reel for video_url upload ({size} bytes, {video_path.name})"
        )

        url = self._host_reel_via_github_contents(video_path)
        if url:
            return url

        userhash = (os.getenv("CATBOX_USERHASH") or "").strip()
        if userhash:
            url = self._host_reel_via_catbox(video_path, userhash=userhash)
            if url:
                return url

        return self._host_reel_via_catbox(video_path, userhash=None)

    def _host_reel_via_github_contents(self, video_path: Path) -> str | None:
        """Upload to a public raw.githubusercontent.com URL (GitHub Actions CI path)."""
        import base64
        import os
        import uuid

        token = (os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip()
        repo_full = (os.getenv("GITHUB_REPOSITORY") or "").strip()
        if not token or not repo_full or "/" not in repo_full:
            return None

        owner, repo_name = repo_full.split("/", 1)
        branch = self.GITHUB_REEL_BRANCH
        path = f"{self.GITHUB_REEL_PREFIX}/{uuid.uuid4().hex}.mp4"
        api = f"https://api.github.com/repos/{owner}/{repo_name}/contents/{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            self._ensure_github_ci_branch(token, owner, repo_name, branch)
            content_b64 = base64.b64encode(video_path.read_bytes()).decode("ascii")
            resp = requests.put(
                api,
                headers=headers,
                json={
                    "message": "ci: temporary reel for Instagram video_url",
                    "content": content_b64,
                    "branch": branch,
                },
                timeout=600,
            )
            if resp.status_code not in (200, 201):
                self.logger.warn(
                    "meta",
                    f"github reel host failed [{resp.status_code}]: {resp.text[:200]}",
                )
                return None

            body = resp.json()
            sha = body.get("content", {}).get("sha", "")
            if not sha:
                self.logger.warn("meta", "github reel host returned no content sha")
                return None

            self._pending_github_reel_cleanup = {
                "owner": owner,
                "repo": repo_name,
                "path": path,
                "branch": branch,
                "sha": sha,
                "token": token,
            }
            url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}/{path}"
            self.logger.info(f"meta | reel public URL ready (github): {url}")
            return url
        except requests.RequestException as exc:
            self.logger.warn("meta", f"github reel host upload failed: {exc}")
            return None

    def _ensure_github_ci_branch(
        self, token: str, owner: str, repo_name: str, branch: str
    ) -> None:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        ref_url = (
            f"https://api.github.com/repos/{owner}/{repo_name}/git/ref/heads/{branch}"
        )
        resp = requests.get(ref_url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return
        if resp.status_code != 404:
            self.logger.warn(
                "meta",
                f"github branch check failed [{resp.status_code}]: {resp.text[:120]}",
            )
            return

        repo_resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo_name}",
            headers=headers,
            timeout=30,
        )
        if repo_resp.status_code != 200:
            return
        default_branch = repo_resp.json().get("default_branch", "master")
        base_resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo_name}/git/ref/heads/{default_branch}",
            headers=headers,
            timeout=30,
        )
        if base_resp.status_code != 200:
            return
        base_sha = base_resp.json().get("object", {}).get("sha", "")
        if not base_sha:
            return

        create_resp = requests.post(
            f"https://api.github.com/repos/{owner}/{repo_name}/git/refs",
            headers=headers,
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
            timeout=30,
        )
        if create_resp.status_code not in (200, 201):
            self.logger.warn(
                "meta",
                f"github branch create failed [{create_resp.status_code}]: "
                f"{create_resp.text[:120]}",
            )

    def _cleanup_github_reel_host(self) -> None:
        info = self._pending_github_reel_cleanup
        self._pending_github_reel_cleanup = None
        if not info:
            return

        owner = info["owner"]
        repo_name = info["repo"]
        path = info["path"]
        headers = {
            "Authorization": f"Bearer {info['token']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            resp = requests.delete(
                f"https://api.github.com/repos/{owner}/{repo_name}/contents/{path}",
                headers=headers,
                json={
                    "message": "ci: remove temporary Instagram reel upload",
                    "sha": info["sha"],
                    "branch": info["branch"],
                },
                timeout=60,
            )
            if resp.status_code in (200, 204):
                self.logger.info("meta | removed temporary github reel host file")
            else:
                self.logger.warn(
                    "meta",
                    f"github reel cleanup failed [{resp.status_code}]: {resp.text[:120]}",
                )
        except requests.RequestException as exc:
            self.logger.warn("meta", f"github reel cleanup failed: {exc}")

    def _host_reel_via_catbox(
        self, video_path: Path, *, userhash: str | None
    ) -> str | None:
        label = "catbox+hash" if userhash else "catbox"
        data: dict[str, str] = {"reqtype": "fileupload"}
        if userhash:
            data["userhash"] = userhash

        try:
            with open(video_path, "rb") as handle:
                resp = requests.post(
                    "https://catbox.moe/user/api.php",
                    data=data,
                    files={
                        "fileToUpload": (
                            video_path.name,
                            handle,
                            "video/mp4",
                        ),
                    },
                    timeout=600,
                )
            if resp.status_code == 200 and resp.text.strip().startswith("http"):
                url = resp.text.strip()
                self.logger.info(f"meta | reel public URL ready ({label}): {url}")
                return url
            self.logger.warn(
                "meta",
                f"{label} reel host failed [{resp.status_code}]: {resp.text[:200]}",
            )
        except requests.RequestException as exc:
            self.logger.warn("meta", f"{label} reel host upload failed: {exc}")
        return None

    def _init_reel_upload_session(
        self,
        caption: str,
        *,
        cover_url: str | None,
    ) -> tuple[str, str]:
        params: dict[str, str] = {
            "access_token": self.access_token,
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption[:2200],
            "share_to_feed": "true",
        }
        if cover_url:
            params["cover_url"] = cover_url

        resp = requests.post(
            f"{self.GRAPH_URL}/{self.ig_user_id}/media",
            params=params,
            timeout=60,
        )
        if resp.status_code >= 400:
            self._log_api_error("reel container", resp)
        resp.raise_for_status()
        body = resp.json()
        container_id = body["id"]
        upload_url = body.get("uri") or f"{self.RUPLOAD_URL}/{container_id}"
        self.logger.info(f"Reel container created: {container_id}")
        return container_id, upload_url

    def _create_reel_container_once(
        self,
        video_path: Path,
        caption: str,
        cover_url: str | None,
    ) -> str:
        """Backward-compatible: create container and upload video."""
        return self._create_reel_container(
            video_path,
            caption,
            cover_url=cover_url,
        )

    def _upload_video_to_container(
        self, container_id: str, file_path: Path, upload_url: str | None = None
    ) -> None:
        """Upload reel bytes via rupload (Meta rejects first-party hosted file_url)."""
        self._resumable_upload_binary(container_id, file_path, upload_url=upload_url)

    def _resumable_upload_binary(
        self,
        container_id: str,
        file_path: Path,
        *,
        upload_url: str | None = None,
    ) -> None:
        file_size = file_path.stat().st_size
        if file_size == 0:
            raise RuntimeError(f"Video file is empty: {file_path}")
        if file_size > 100 * 1024 * 1024:
            raise RuntimeError(
                f"Video too large for Instagram upload ({file_size / (1024 * 1024):.1f} MiB)"
            )

        target_url = upload_url or f"{self.RUPLOAD_URL}/{container_id}"
        data = file_path.read_bytes()

        if file_size <= self.SINGLE_UPLOAD_MAX_BYTES:
            try:
                self._rupload_post_chunk(target_url, data, offset=0, file_size=file_size)
                self.logger.info(
                    f"Uploaded {file_path.name} ({file_size} bytes) via single-request rupload"
                )
                return
            except RuntimeError:
                transferred = self._query_bytes_transferred(container_id)
                if transferred and 0 < transferred < file_size:
                    self.logger.warn(
                        "meta",
                        f"single-request rupload stalled at {transferred}/{file_size} — resuming chunked",
                    )
                    self._rupload_chunked(
                        target_url,
                        data,
                        file_size=file_size,
                        start_offset=transferred,
                    )
                    self.logger.info(
                        f"Uploaded {file_path.name} ({file_size} bytes) via resumed chunked rupload"
                    )
                    return
                raise

        self._rupload_chunked(target_url, data, file_size=file_size)
        self.logger.info(
            f"Uploaded {file_path.name} ({file_size} bytes) via chunked rupload "
            f"({self.CHUNK_SIZE_BYTES // 1024}KB chunks)"
        )

    def _rupload_chunked(
        self,
        target_url: str,
        data: bytes,
        *,
        file_size: int,
        start_offset: int = 0,
        chunk_size: int | None = None,
    ) -> None:
        chunk_size = chunk_size or self.CHUNK_SIZE_BYTES
        offset = start_offset
        while offset < file_size:
            chunk = data[offset:offset + chunk_size]
            if not chunk:
                break
            self._rupload_post_chunk(
                target_url,
                chunk,
                offset=offset,
                file_size=file_size,
            )
            offset += len(chunk)

    def _rupload_post_chunk(
        self,
        target_url: str,
        chunk: bytes,
        *,
        offset: int,
        file_size: int,
    ) -> None:
        headers = {
            "Authorization": f"OAuth {self.access_token}",
            "offset": str(offset),
            "file_size": str(file_size),
            "Content-Type": "application/octet-stream",
        }
        resp = requests.post(
            target_url,
            headers=headers,
            data=chunk,
            timeout=600,
        )
        if resp.status_code not in (200, 206):
            self._log_api_error("rupload binary", resp)
            raise RuntimeError(
                f"rupload failed at offset {offset} ({resp.status_code}): {resp.text[:500]}"
            )

    def _validate_reel_for_upload(self, video_path: Path) -> None:
        """ffprobe check — log specs; warn if outside typical Instagram reel constraints."""
        import json
        import subprocess

        from src.utils.ffmpeg_path import get_ffmpeg_exe

        result = subprocess.run(
            [
                get_ffmpeg_exe(),
                "-hide_banner",
                "-i",
                str(video_path),
            ],
            capture_output=True,
            text=True,
        )
        stderr = result.stderr or ""
        summary_parts: list[str] = [
            f"size={video_path.stat().st_size}",
            f"size_mb={video_path.stat().st_size / (1024 * 1024):.2f}",
        ]
        for line in stderr.splitlines():
            if "Video:" in line or "Audio:" in line or "Duration:" in line:
                summary_parts.append(line.strip())

        probe = subprocess.run(
            [
                get_ffmpeg_exe(),
                "-hide_banner",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(video_path),
            ],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0 and probe.stdout:
            try:
                info = json.loads(probe.stdout)
                for stream in info.get("streams", []):
                    if stream.get("codec_type") == "video":
                        summary_parts.append(
                            f"v={stream.get('codec_name')} "
                            f"{stream.get('width')}x{stream.get('height')} "
                            f"profile={stream.get('profile')} "
                            f"fps={stream.get('r_frame_rate')}"
                        )
                    elif stream.get("codec_type") == "audio":
                        summary_parts.append(
                            f"a={stream.get('codec_name')} "
                            f"rate={stream.get('sample_rate')}"
                        )
            except json.JSONDecodeError:
                pass

        self.logger.info("meta | reel upload spec: " + " | ".join(summary_parts))

    def _query_bytes_transferred(self, container_id: str) -> int | None:
        try:
            resp = requests.get(
                f"{self.GRAPH_URL}/{container_id}",
                params={
                    "access_token": self.access_token,
                    "fields": "status_code,video_status",
                },
                timeout=30,
            )
            if resp.status_code != 200:
                return None
            vs = resp.json().get("video_status") or {}
            upload_phase = vs.get("uploading_phase") or {}
            transferred = upload_phase.get("bytes_transferred")
            if transferred is None:
                return None
            return int(transferred)
        except (requests.RequestException, TypeError, ValueError):
            return None

    def _log_upload_bytes_transferred(self, container_id: str) -> None:
        transferred = self._query_bytes_transferred(container_id)
        if transferred is not None:
            self.logger.warn(
                "meta",
                f"rupload progress bytes_transferred={transferred}",
            )

    def _prepare_reel_for_instagram(self, video_path: Path) -> Path:
        """Re-encode to H.264/AAC + faststart and enforce Instagram reel size/duration caps."""
        import subprocess
        import tempfile

        from src.utils.ffmpeg_path import get_ffmpeg_exe, get_media_duration

        max_sec = float(getattr(self.config.video, "instagram_max_sec", 90))
        max_bytes = int(
            getattr(self.config.video, "instagram_max_upload_mb", 12) * 1024 * 1024
        )
        encode_profiles = [
            ("24", "2000k", "4000k"),
            ("26", "1500k", "3000k"),
            ("28", "1200k", "2400k"),
        ]

        out = Path(tempfile.mkstemp(suffix="_ig.mp4")[1])
        ffmpeg = get_ffmpeg_exe()
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
        )
        audio_codec = probe_audio_codec(video_path)
        preserve_audio = audio_codec == "aac"
        if preserve_audio:
            self.logger.info("meta | preserving assembled AAC audio (keeps BGM bed intact)")
        else:
            self.logger.warn(
                "meta",
                f"re-encode audio from {audio_codec or 'unknown'} — BGM may need louder mix",
            )

        for crf, maxrate, bufsize in encode_profiles:
            cmd = [
                ffmpeg, "-y",
                "-i", str(video_path),
                "-t", str(max_sec),
                "-vf", vf,
                "-map", "0:v:0", "-map", "0:a:0",
                "-c:v", "libx264", "-preset", "fast", "-crf", crf,
                "-profile:v", "main", "-level", "4.0", "-pix_fmt", "yuv420p",
                "-r", "30", "-vsync", "cfr", "-g", "60", "-keyint_min", "60",
                "-maxrate", maxrate, "-bufsize", bufsize,
                "-movflags", "+faststart",
                str(out),
            ]
            if preserve_audio:
                audio_args = ["-c:a", "copy"]
            else:
                audio_args = [
                    "-af", "alimiter=limit=0.95",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
                ]
            insert_at = cmd.index("-movflags")
            cmd[insert_at:insert_at] = audio_args
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Instagram video prep failed: {result.stderr[-800:]}")
            if out.stat().st_size <= max_bytes:
                break
            self.logger.warn(
                "meta",
                f"prepared reel {out.stat().st_size} bytes > {max_bytes} — retrying lower bitrate",
            )

        final_dur = get_media_duration(out)
        final_size = out.stat().st_size
        if final_size > max_bytes:
            self.logger.warn(
                "meta",
                f"prepared reel still {final_size} bytes after bitrate retries (cap {max_bytes})",
            )
        self.logger.info(
            f"meta | prepared reel for upload: {final_size} bytes, {final_dur:.1f}s"
        )
        return out

    def _resumable_upload(self, container_id: str, file_path: Path) -> None:
        """Backward-compatible alias."""
        self._upload_video_to_container(container_id, file_path)

    def _wait_and_publish(
        self, container_id: str, *, publish_at: datetime | None = None
    ) -> str | None:
        for attempt in range(self.POLL_MAX_ATTEMPTS):
            resp = requests.get(
                f"{self.GRAPH_URL}/{container_id}",
                params={
                    "access_token": self.access_token,
                    "fields": "status_code,status",
                },
                timeout=30,
            )
            resp.raise_for_status()
            status = resp.json().get("status_code", "")
            if status == "FINISHED":
                break
            if status == "ERROR":
                raise RuntimeError(
                    f"Container {container_id} failed: {resp.json().get('status')}"
                )
            time.sleep(self.POLL_INTERVAL_SEC)
        else:
            raise TimeoutError(f"Container {container_id} did not finish in time")

        params: dict[str, str] = {
            "access_token": self.access_token,
            "creation_id": container_id,
        }
        # Instagram Graph API publishes immediately — scheduling is handled by our publish job.

        resp = requests.post(
            f"{self.GRAPH_URL}/{self.ig_user_id}/media_publish",
            params=params,
            timeout=60,
        )
        publish_started = datetime.now(ZoneInfo("UTC"))
        publish_id = self._media_publish_with_retry(
            resp, container_id, publish_started=publish_started
        )
        self.logger.info(f"Published container {container_id} → {publish_id}")
        return publish_id or None

    def _media_publish_with_retry(
        self,
        resp: requests.Response,
        container_id: str,
        *,
        publish_started: datetime | None = None,
    ) -> str:
        publish_started = publish_started or datetime.now(ZoneInfo("UTC"))
        for attempt in range(self.RATE_LIMIT_RETRY_ATTEMPTS):
            if resp.status_code < 400:
                return resp.json().get("id", "")

            if self._is_ambiguous_publish_error(resp):
                recovered = self._recover_publish_id(
                    container_id, since=publish_started
                )
                if recovered:
                    self.logger.warn(
                        "meta",
                        f"media_publish ambiguous error for {container_id} — "
                        f"recovered publish id {recovered}",
                    )
                    return recovered
                self.logger.warn(
                    "meta",
                    f"media_publish ambiguous error for {container_id} — "
                    "no matching recent media found",
                )
                self._log_api_error("media_publish", resp)
                resp.raise_for_status()

            if self._is_rate_limited(resp) and attempt < self.RATE_LIMIT_RETRY_ATTEMPTS - 1:
                recovered = self._recover_publish_id(
                    container_id, since=publish_started
                )
                if recovered:
                    self.logger.warn(
                        "meta",
                        f"media_publish rate limited but publish recovered: {recovered}",
                    )
                    return recovered

                wait = self.RATE_LIMIT_RETRY_BASE_SEC * (2 ** attempt)
                self.logger.warn(
                    "meta",
                    f"media_publish rate limited for {container_id} — "
                    f"retry in {wait}s ({attempt + 1}/{self.RATE_LIMIT_RETRY_ATTEMPTS})",
                )
                time.sleep(wait)
                recovered = self._recover_publish_id(
                    container_id, since=publish_started
                )
                if recovered:
                    return recovered
                resp = requests.post(
                    f"{self.GRAPH_URL}/{self.ig_user_id}/media_publish",
                    params={
                        "access_token": self.access_token,
                        "creation_id": container_id,
                    },
                    timeout=60,
                )
                continue

            self._log_api_error("media_publish", resp)
            resp.raise_for_status()

        raise RuntimeError(f"media_publish failed for {container_id} after rate-limit retries")

    @staticmethod
    def _parse_error_payload(resp: requests.Response) -> dict:
        try:
            err = resp.json().get("error", {})
            return err if isinstance(err, dict) else {}
        except (ValueError, AttributeError, TypeError):
            return {}

    def _is_ambiguous_publish_error(self, resp: requests.Response) -> bool:
        err = self._parse_error_payload(resp)
        subcode = err.get("error_subcode")
        message = (err.get("message") or "").lower()
        if subcode in self.PUBLISH_AMBIGUOUS_SUBCODES:
            return True
        if err.get("code") == -1 and "fatal" in message:
            return True
        return False

    def _is_rate_limited(self, resp: requests.Response) -> bool:
        if resp.status_code == 429:
            return True
        if self._is_ambiguous_publish_error(resp):
            return False
        try:
            err = self._parse_error_payload(resp)
            code = err.get("code")
            subcode = err.get("error_subcode")
            message = (err.get("message") or "").lower()
            if code in self.PUBLISH_RATE_LIMIT_CODES:
                return True
            if subcode in self.PUBLISH_RATE_LIMIT_SUBCODES:
                return True
            if "request limit" in message or "rate limit" in message:
                return True
        except (ValueError, AttributeError, TypeError):
            pass
        return False

    def _get_container_status(self, container_id: str) -> dict:
        try:
            resp = requests.get(
                f"{self.GRAPH_URL}/{container_id}",
                params={
                    "access_token": self.access_token,
                    "fields": "status_code,status",
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException:
            pass
        return {}

    def _fetch_recent_media(self, limit: int = 10) -> list[dict]:
        try:
            resp = requests.get(
                f"{self.GRAPH_URL}/{self.ig_user_id}/media",
                params={
                    "access_token": self.access_token,
                    "fields": "id,media_type,timestamp",
                    "limit": str(limit),
                },
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                return data if isinstance(data, list) else []
        except requests.RequestException:
            pass
        return []

    @staticmethod
    def _parse_media_timestamp(ts: str) -> datetime | None:
        if not ts:
            return None
        try:
            normalized = ts.replace("+0000", "+00:00").replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=ZoneInfo("UTC"))
            return parsed
        except (ValueError, TypeError):
            return None

    def _recover_publish_id(
        self,
        container_id: str,
        *,
        since: datetime | None = None,
        media_type: str | None = None,
    ) -> str | None:
        status = self._get_container_status(container_id)
        status_code = (status.get("status_code") or "").upper()
        if status_code == "ERROR":
            return None

        since_utc = since or datetime.now(ZoneInfo("UTC"))
        if since_utc.tzinfo is None:
            since_utc = since_utc.replace(tzinfo=ZoneInfo("UTC"))
        else:
            since_utc = since_utc.astimezone(ZoneInfo("UTC"))
        window_start = since_utc - timedelta(minutes=2)
        window_end = since_utc + timedelta(minutes=self.PUBLISH_RECOVERY_WINDOW_MIN)

        for item in self._fetch_recent_media(limit=15):
            media_id = item.get("id")
            if not media_id:
                continue
            if media_type and item.get("media_type") != media_type:
                continue
            posted = self._parse_media_timestamp(item.get("timestamp", ""))
            if posted is None:
                continue
            posted_utc = posted.astimezone(ZoneInfo("UTC"))
            if window_start <= posted_utc <= window_end:
                return str(media_id)
        return None

    @staticmethod
    def _classify_publish_error(exc: Exception) -> str:
        text = str(exc).lower()
        if "2207085" in text or "ambiguous" in text:
            return "ambiguous_publish"
        if "request limit" in text or "rate limit" in text or "403" in text:
            return "rate_limit"
        if isinstance(exc, TimeoutError):
            return "timeout"
        return "api_error"

    def _upload_image_container(self, image_path: Path) -> str:
        """Upload a single image as carousel child; returns container ID."""
        image_url = self._upload_image_as_public_url(image_path)
        if not image_url:
            raise RuntimeError(f"Failed to upload carousel image: {image_path.name}")

        resp = requests.post(
            f"{self.GRAPH_URL}/{self.ig_user_id}/media",
            params={
                "access_token": self.access_token,
                "image_url": image_url,
                "is_carousel_item": "true",
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def _create_carousel_container(
        self,
        image_paths: list[Path],
        caption: str,
        *,
        publish_at: datetime | None = None,
    ) -> str:
        del publish_at
        child_ids: list[str] = []
        for i, img_path in enumerate(image_paths):
            child_id = self._upload_image_container(img_path)
            self._wait_container_ready(child_id)
            child_ids.append(child_id)
            if i + 1 < len(image_paths):
                time.sleep(self.CAROUSEL_CHILD_UPLOAD_DELAY_SEC)

        params: dict[str, str] = {
            "access_token": self.access_token,
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption[:2200],
        }

        resp = requests.post(
            f"{self.GRAPH_URL}/{self.ig_user_id}/media",
            params=params,
            timeout=60,
        )
        if resp.status_code >= 400:
            self._log_api_error("carousel container", resp)
        resp.raise_for_status()
        container_id = resp.json()["id"]
        self.logger.info(f"Carousel container created: {container_id} ({len(child_ids)} slides)")
        return container_id

    def _wait_container_ready(self, container_id: str) -> None:
        for _ in range(self.POLL_MAX_ATTEMPTS):
            resp = requests.get(
                f"{self.GRAPH_URL}/{container_id}",
                params={
                    "access_token": self.access_token,
                    "fields": "status_code",
                },
                timeout=30,
            )
            resp.raise_for_status()
            if resp.json().get("status_code") == "FINISHED":
                return
            time.sleep(2)
        raise TimeoutError(f"Image container {container_id} not ready")

    def _upload_cover_image(self, thumbnail_path: Path) -> str | None:
        """Upload thumbnail to Facebook as unpublished photo; return public URL."""
        return self._upload_image_as_public_url(thumbnail_path)

    def _upload_image_as_public_url(self, image_path: Path) -> str | None:
        if not self.page_id:
            self.logger.warn("meta", "META_PAGE_ID missing — cannot host images for API")
            return None
        try:
            with open(image_path, "rb") as f:
                resp = requests.post(
                    f"{self.GRAPH_URL}/{self.page_id}/photos",
                    data={
                        "access_token": self.access_token,
                        "published": "false",
                        "temporary": "true",
                    },
                    files={"source": (image_path.name, f, "image/png")},
                    timeout=60,
                )
            if resp.status_code >= 400:
                self._log_api_error("page photo upload", resp)
                return None
            photo_id = resp.json().get("id")
            if not photo_id:
                return None
            url_resp = requests.get(
                f"{self.GRAPH_URL}/{photo_id}",
                params={"access_token": self.access_token, "fields": "images"},
                timeout=30,
            )
            if url_resp.status_code >= 400:
                self._log_api_error("photo url lookup", url_resp)
                return None
            images = url_resp.json().get("images", [])
            if images:
                return images[0].get("source")
        except requests.RequestException as exc:
            self.logger.warn("meta", f"image upload failed: {exc}")
        return None

    def search_hashtags(self, queries: list[str], limit: int = 10) -> list[str]:
        """Search Instagram hashtags via Graph API; returns ranked tag names."""
        if not self.is_configured():
            return []

        found: list[tuple[int, str]] = []
        seen: set[str] = set()

        for query in queries:
            q = query.lstrip("#").lower()
            if not q or q in seen:
                continue
            try:
                resp = requests.get(
                    f"{self.GRAPH_URL}/ig_hashtag_search",
                    params={
                        "access_token": self.access_token,
                        "user_id": self.ig_user_id,
                        "q": q,
                    },
                    timeout=30,
                )
                if resp.status_code != 200:
                    continue
                for item in resp.json().get("data", []):
                    tag_id = item.get("id")
                    if not tag_id:
                        continue
                    info = requests.get(
                        f"{self.GRAPH_URL}/{tag_id}",
                        params={
                            "access_token": self.access_token,
                            "fields": "name",
                        },
                        timeout=15,
                    )
                    if info.status_code == 200:
                        name = info.json().get("name", "").lower()
                        if name and name not in seen:
                            seen.add(name)
                            found.append((len(found), f"#{name}"))
            except requests.RequestException:
                continue

        return [tag for _, tag in found[:limit]]

    def _save_manual_package(
        self,
        reel_path: Path,
        static_paths: list[Path],
        caption: str,
        bundle_id: str,
        thumbnail_path: Path | None,
    ) -> str:
        import shutil

        package_dir = self.config.path("output_dir") / "ready_to_upload" / bundle_id
        package_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(reel_path, package_dir / "reel.mp4")
        if thumbnail_path and thumbnail_path.exists():
            shutil.copy2(thumbnail_path, package_dir / "thumbnail.png")
        for i, sp in enumerate(static_paths):
            shutil.copy2(sp, package_dir / f"static_post_{i + 1:02d}.png")
        if static_paths:
            shutil.copy2(static_paths[0], package_dir / "static_post.png")
        (package_dir / "caption.txt").write_text(caption, encoding="utf-8")
        (package_dir / "UPLOAD_INSTRUCTIONS.txt").write_text(
            "Meta API not configured. Upload manually:\n"
            "1. reel.mp4 as Instagram Reel (use thumbnail.png as cover)\n"
            f"2. static_post_*.png as carousel ({len(static_paths)} slides)\n"
            f"Scheduled time: {self.config.post_time} {self.config.timezone}\n",
            encoding="utf-8",
        )
        return f"manual_package:{bundle_id}"

    def _save_carousel_fallback(
        self,
        static_paths: list[Path],
        caption: str,
        bundle_id: str,
        reason: str,
    ) -> Path:
        import shutil

        package_dir = self.config.path("output_dir") / "ready_to_upload" / bundle_id
        package_dir.mkdir(parents=True, exist_ok=True)
        for i, sp in enumerate(static_paths):
            shutil.copy2(sp, package_dir / f"static_post_{i + 1:02d}.png")
        if static_paths:
            shutil.copy2(static_paths[0], package_dir / "static_post.png")
        (package_dir / "caption.txt").write_text(caption, encoding="utf-8")
        (package_dir / "CAROUSEL_UPLOAD.txt").write_text(
            "Reel was published successfully. Carousel failed via API.\n"
            f"Reason: {reason}\n"
            f"Upload static_post_*.png as an Instagram carousel with caption.txt\n",
            encoding="utf-8",
        )
        self.logger.info(f"meta | saved carousel fallback package: {package_dir}")
        return package_dir

    def _log_api_error(self, step: str, resp: requests.Response) -> None:
        try:
            detail = resp.json().get("error", {})
            message = detail.get("message", resp.text[:300])
            code = detail.get("code", resp.status_code)
            subcode = detail.get("error_subcode", "")
            self.logger.warn("meta", f"{step} failed [{code}/{subcode}]: {message}")
        except (ValueError, AttributeError):
            self.logger.warn("meta", f"{step} failed: {resp.text[:300]}")

    @staticmethod
    def inspect_token(token: str, app_id: str = "", app_secret: str = "") -> dict:
        """Return token type, app id, and granted scopes from Graph debug_token."""
        token = (token or "").strip()
        if not token:
            return {"ok": False, "error": "No token"}

        app_id = (app_id or "").strip()
        app_secret = (app_secret or "").strip()
        app_token = f"{app_id}|{app_secret}" if app_id and app_secret else token

        resp = requests.get(
            "https://graph.facebook.com/v21.0/debug_token",
            params={"input_token": token, "access_token": app_token},
            timeout=30,
        )
        if resp.status_code != 200:
            err = resp.json().get("error", {})
            return {"ok": False, "error": err.get("message", resp.text)}

        data = resp.json().get("data", {})
        expires_at = data.get("expires_at")
        expires_label = "never (Page token)" if expires_at == 0 else str(expires_at)
        return {
            "ok": True,
            "type": data.get("type", "?"),
            "app_id": data.get("app_id"),
            "is_valid": data.get("is_valid"),
            "scopes": data.get("scopes", []) or [],
            "expires_at": expires_at,
            "expires_label": expires_label,
        }

    @staticmethod
    def validate_app_credentials(app_id: str, app_secret: str) -> dict:
        """Verify META_APP_ID + META_APP_SECRET pair (client credentials grant)."""
        app_id = (app_id or "").strip()
        app_secret = (app_secret or "").strip()
        if not app_id or not app_secret:
            return {"ok": False, "error": "META_APP_ID and META_APP_SECRET required"}

        resp = requests.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={
                "client_id": app_id,
                "client_secret": app_secret,
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            err = resp.json().get("error", {})
            msg = err.get("message", resp.text)
            if "client secret" in msg.lower():
                return {
                    "ok": False,
                    "error": (
                        "META_APP_SECRET is wrong for META_APP_ID. "
                        "Copy a fresh App Secret from Meta Developers → Your App → "
                        "App settings → Basic (Show → copy). "
                        "Use the SAME app in Graph API Explorer."
                    ),
                }
            return {"ok": False, "error": msg}
        return {"ok": True, "app_access_token": resp.json().get("access_token", "")}

    @staticmethod
    def exchange_long_lived_user_token(
        short_token: str, app_id: str, app_secret: str
    ) -> dict:
        """Exchange short-lived user token for long-lived user token (~60 days)."""
        short_token = (short_token or "").strip()
        app_id = (app_id or "").strip()
        app_secret = (app_secret or "").strip()
        if not short_token:
            return {"ok": False, "error": "No user token"}
        if not app_id or not app_secret:
            return {
                "ok": False,
                "error": "META_APP_ID and META_APP_SECRET required in .env for long-lived exchange",
            }

        resp = requests.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": short_token,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            err = resp.json().get("error", {})
            return {"ok": False, "error": err.get("message", resp.text)}

        body = resp.json()
        token = body.get("access_token", "")
        if not token:
            return {"ok": False, "error": "No access_token in exchange response"}
        return {
            "ok": True,
            "access_token": token,
            "expires_in": body.get("expires_in"),
        }

    @staticmethod
    def obtain_permanent_page_token(
        short_user_token: str,
        app_id: str,
        app_secret: str,
        page_id: str = "",
    ) -> dict:
        """
        Get a Page access token that does not expire (Meta's standard automation path).

        1. Short user token → long-lived user token (needs app id + secret)
        2. Long-lived user → Page access token (never expires unless revoked)
        """
        exchange = MetaScheduler.exchange_long_lived_user_token(
            short_user_token, app_id, app_secret
        )
        if not exchange["ok"]:
            return exchange

        long_token = exchange["access_token"]
        pages_result = MetaScheduler.discover_accounts(long_token)
        if not pages_result["ok"]:
            return pages_result

        pages = pages_result.get("pages") or []
        target_page_id = (page_id or "").strip()

        chosen: dict | None = None
        if target_page_id:
            for p in pages:
                if p.get("id") == target_page_id:
                    chosen = p
                    break
            if not chosen:
                page_result = MetaScheduler.fetch_page_token(long_token, target_page_id)
                if page_result["ok"]:
                    chosen = {
                        "id": page_result["page"].get("id"),
                        "name": page_result["page"].get("name"),
                        "access_token": page_result["page_token"],
                        "instagram_business_account": None,
                    }
        elif pages:
            chosen = pages[0]

        if not chosen or not chosen.get("access_token"):
            return {
                "ok": False,
                "error": "Could not obtain Page token. Check META_PAGE_ID and Page Admin access.",
            }

        page_token = chosen["access_token"]
        token_info = MetaScheduler.inspect_token(page_token, app_id, app_secret)
        ig = chosen.get("instagram_business_account") or {}

        return {
            "ok": True,
            "page_id": chosen.get("id"),
            "page_name": chosen.get("name"),
            "page_token": page_token,
            "ig_user_id": ig.get("id"),
            "ig_username": ig.get("username"),
            "token_info": token_info,
            "long_lived_user_expires_in": exchange.get("expires_in"),
        }

    @staticmethod
    def probe_photo_upload(config: AppConfig) -> dict:
        """Try uploading a tiny PNG to the Page (carousel + cover need this)."""
        token = (config.meta_access_token or "").strip()
        page_id = (config.meta_page_id or "").strip()
        if not token or not page_id:
            return {"ok": False, "error": "META_ACCESS_TOKEN or META_PAGE_ID missing"}

        # 1x1 transparent PNG
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        try:
            resp = requests.post(
                f"https://graph.facebook.com/v21.0/{page_id}/photos",
                data={
                    "access_token": token,
                    "published": "false",
                    "temporary": "true",
                },
                files={"source": ("probe.png", png, "image/png")},
                timeout=60,
            )
        except requests.RequestException as exc:
            return {"ok": False, "error": str(exc)}

        if resp.status_code == 200:
            return {"ok": True, "photo_id": resp.json().get("id")}

        err = resp.json().get("error", {})
        return {
            "ok": False,
            "error": err.get("message", resp.text),
            "code": err.get("code"),
            "subcode": err.get("error_subcode"),
        }

    @staticmethod
    def verify_connection(config: AppConfig) -> dict:
        """Test Meta API credentials and return account info."""
        token = (config.meta_access_token or "").strip()
        ig_id = (config.meta_ig_user_id or "").strip()
        if not token or not ig_id:
            return {"ok": False, "error": "META_ACCESS_TOKEN or META_IG_USER_ID missing"}
        if not token.startswith("EAA"):
            return {
                "ok": False,
                "error": "META_ACCESS_TOKEN must start with EAA (Facebook Graph API token)",
            }

        resp = requests.get(
            f"https://graph.facebook.com/v21.0/{ig_id}",
            params={
                "access_token": token,
                "fields": "id,username,name,profile_picture_url",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return {"ok": False, "error": resp.json().get("error", {}).get("message", resp.text)}

        token_info = MetaScheduler.inspect_token(
            token, config.meta_app_id, config.meta_app_secret
        )
        photo_probe = MetaScheduler.probe_photo_upload(config)
        missing = []
        if token_info.get("ok"):
            scopes = set(token_info.get("scopes", []))
            missing = [p for p in MetaScheduler.PHOTO_PERMISSIONS if p not in scopes]

        return {
            "ok": True,
            "account": resp.json(),
            "token_info": token_info,
            "photo_probe": photo_probe,
            "missing_photo_permissions": missing,
        }

    @staticmethod
    def discover_accounts(token: str) -> dict:
        """List Facebook Pages + linked Instagram IDs for a Graph API user token."""
        token = (token or "").strip()
        if not token:
            return {"ok": False, "error": "No token provided"}
        if token.startswith("IGA"):
            return {
                "ok": False,
                "error": (
                    "This looks like an Instagram Login token (IGA...). "
                    "Rahasya needs a Facebook Graph API token (EAA...) from Graph API Explorer."
                ),
            }
        if not token.startswith("EAA") and not token.startswith("EAAG"):
            return {
                "ok": False,
                "error": "Token must be a Facebook Graph API token (usually starts with EAA...)",
            }

        me = requests.get(
            "https://graph.facebook.com/v21.0/me",
            params={"access_token": token, "fields": "id,name"},
            timeout=30,
        )
        if me.status_code != 200:
            err = me.json().get("error", {})
            return {"ok": False, "error": err.get("message", me.text)}

        pages: list[dict] = []
        url = "https://graph.facebook.com/v21.0/me/accounts"
        params = {
            "access_token": token,
            "fields": "id,name,access_token,instagram_business_account{id,username,name}",
            "limit": "100",
        }
        while url:
            resp = requests.get(url, params=params if "me/accounts" in url else None, timeout=30)
            if resp.status_code != 200:
                err = resp.json().get("error", {})
                return {"ok": False, "error": err.get("message", resp.text)}
            body = resp.json()
            pages.extend(body.get("data", []))
            next_url = body.get("paging", {}).get("next")
            url = next_url or ""
            params = {}

        return {
            "ok": True,
            "user": me.json(),
            "pages": pages,
        }

    @staticmethod
    def fetch_page_token(user_token: str, page_id: str) -> dict:
        """Get Page access token when /me/accounts is empty but PAGE_ID is known."""
        user_token = (user_token or "").strip()
        page_id = (page_id or "").strip()
        if not user_token or not page_id:
            return {"ok": False, "error": "Need user token and page id"}

        resp = requests.get(
            f"https://graph.facebook.com/v21.0/{page_id}",
            params={"access_token": user_token, "fields": "id,name,access_token"},
            timeout=30,
        )
        if resp.status_code != 200:
            err = resp.json().get("error", {})
            return {"ok": False, "error": err.get("message", resp.text)}

        data = resp.json()
        page_token = data.get("access_token", "")
        if not page_token:
            return {
                "ok": False,
                "error": (
                    "No page token returned — your Facebook user may not be Admin on this Page. "
                    "Add yourself as Page Admin or create a new Page with this Facebook account."
                ),
            }
        return {"ok": True, "page": data, "page_token": page_token}
