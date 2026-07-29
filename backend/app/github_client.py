import json
import re
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import jwt

from .errors import DomainError


class GitHubAppClient:
    check_name = "DeployGuard change risk"

    def __init__(
        self,
        *,
        app_id: str,
        private_key: str,
        api_url: str,
        api_version: str,
    ) -> None:
        self.app_id = app_id
        self.private_key = private_key.replace("\\n", "\n")
        self.api_url = api_url.rstrip("/")
        self.api_version = api_version

    def installation(self, installation_id: str) -> dict:
        return self._request(
            "GET",
            f"/app/installations/{installation_id}",
            token=self._app_jwt(),
        )

    def list_installation_repositories(
        self, installation_id: str
    ) -> list[dict]:
        token = self._installation_token(installation_id)
        repositories: list[dict] = []
        page = 1
        while True:
            payload = self._request(
                "GET",
                f"/installation/repositories?per_page=100&page={page}",
                token=token,
            )
            batch = payload.get("repositories", [])
            repositories.extend(batch)
            if len(batch) < 100:
                return repositories
            page += 1
            if page > 100:
                raise DomainError(
                    "GitHub repository pagination exceeded the safety limit",
                    "github_pagination_limit",
                    502,
                )

    def create_check_run(
        self,
        *,
        installation_id: str,
        repository_full_name: str,
        head_sha: str,
        external_id: str,
        conclusion: str,
        title: str,
        summary: str,
        details_url: str | None = None,
    ) -> dict:
        """Publish a completed, evidence-only risk result to a GitHub commit."""
        owner, repository = self._repository_parts(repository_full_name)
        body = self._check_run_body(
            head_sha=head_sha,
            external_id=external_id,
            conclusion=conclusion,
            title=title,
            summary=summary,
            details_url=details_url,
            include_head=True,
        )
        return self._request(
            "POST",
            (
                f"/repos/{quote(owner, safe='')}/"
                f"{quote(repository, safe='')}/check-runs"
            ),
            token=self._installation_token(installation_id),
            body=body,
        )

    def update_check_run(
        self,
        *,
        installation_id: str,
        repository_full_name: str,
        provider_check_id: str,
        head_sha: str,
        external_id: str,
        conclusion: str,
        title: str,
        summary: str,
        details_url: str | None = None,
    ) -> dict:
        """Update a known Check Run instead of creating duplicate results."""
        owner, repository = self._repository_parts(repository_full_name)
        if not provider_check_id.isdigit():
            raise DomainError(
                "GitHub check run input is invalid",
                "github_check_input_invalid",
                400,
            )
        body = self._check_run_body(
            head_sha=head_sha,
            external_id=external_id,
            conclusion=conclusion,
            title=title,
            summary=summary,
            details_url=details_url,
            include_head=False,
        )
        return self._request(
            "PATCH",
            (
                f"/repos/{quote(owner, safe='')}/"
                f"{quote(repository, safe='')}/check-runs/"
                f"{quote(provider_check_id, safe='')}"
            ),
            token=self._installation_token(installation_id),
            body=body,
        )

    def find_check_run(
        self,
        *,
        installation_id: str,
        repository_full_name: str,
        head_sha: str,
        external_id: str,
    ) -> dict | None:
        """Recover a Check Run after an uncertain create response."""
        owner, repository = self._repository_parts(repository_full_name)
        if (
            not re.fullmatch(r"[0-9a-fA-F]{7,64}", head_sha)
            or not external_id.strip()
        ):
            raise DomainError(
                "GitHub check run input is invalid",
                "github_check_input_invalid",
                400,
            )
        payload = self._request(
            "GET",
            (
                f"/repos/{quote(owner, safe='')}/"
                f"{quote(repository, safe='')}/commits/"
                f"{quote(head_sha, safe='')}/check-runs"
                f"?check_name={quote(self.check_name, safe='')}"
                "&filter=all&per_page=100"
            ),
            token=self._installation_token(installation_id),
        )
        records = payload.get("check_runs")
        if not isinstance(records, list):
            raise DomainError(
                "GitHub returned an invalid Check Runs response",
                "github_api_invalid_response",
                502,
            )
        for record in records:
            if (
                isinstance(record, dict)
                and str(record.get("external_id") or "") == external_id
            ):
                return record
        return None

    def _repository_parts(self, repository_full_name: str) -> tuple[str, str]:
        owner, separator, repository = repository_full_name.partition("/")
        if (
            not separator
            or not owner
            or not repository
            or "/" in repository
        ):
            raise DomainError(
                "GitHub check run input is invalid",
                "github_check_input_invalid",
                400,
            )
        return owner, repository

    def _check_run_body(
        self,
        *,
        head_sha: str,
        external_id: str,
        conclusion: str,
        title: str,
        summary: str,
        details_url: str | None,
        include_head: bool,
    ) -> dict[str, object]:
        if (
            not re.fullmatch(r"[0-9a-fA-F]{7,64}", head_sha)
            or not external_id.strip()
            or conclusion
            not in {"action_required", "failure", "neutral", "success"}
        ):
            raise DomainError(
                "GitHub check run input is invalid",
                "github_check_input_invalid",
                400,
            )
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        body: dict[str, object] = {
            "name": self.check_name,
            "status": "completed",
            "conclusion": conclusion,
            "external_id": external_id,
            "completed_at": now,
            "output": {
                "title": title[:255],
                "summary": summary[:65_535],
            },
        }
        if include_head:
            body["head_sha"] = head_sha
        if details_url:
            body["details_url"] = details_url
        return body

    def _installation_token(self, installation_id: str) -> str:
        payload = self._request(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            token=self._app_jwt(),
            body={},
        )
        token = payload.get("token")
        if not isinstance(token, str) or not token:
            raise DomainError(
                "GitHub did not return an installation token",
                "github_token_exchange_failed",
                502,
            )
        return token

    def _app_jwt(self) -> str:
        if not self.app_id or not self.private_key:
            raise DomainError(
                "GitHub App is not configured", "github_app_not_configured", 503
            )
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "iat": int((now - timedelta(seconds=60)).timestamp()),
                "exp": int((now + timedelta(minutes=9)).timestamp()),
                "iss": self.app_id,
            },
            self.private_key,
            algorithm="RS256",
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        body: dict | None = None,
    ) -> dict:
        request = Request(
            f"{self.api_url}{path}",
            method=method,
            data=(
                json.dumps(body).encode("utf-8") if body is not None else None
            ),
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "DeployGuard-AI",
                "X-GitHub-Api-Version": self.api_version,
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            retry_after = error.headers.get("Retry-After")
            rate_limit_remaining = error.headers.get(
                "X-RateLimit-Remaining"
            )
            if error.code in {403, 429} and (
                retry_after or rate_limit_remaining == "0"
            ):
                code = "github_rate_limited"
            elif error.code >= 500 or error.code in {408, 409, 425}:
                code = "github_api_unavailable"
            else:
                code = "github_api_rejected"
            raise DomainError(
                f"GitHub API request failed with status {error.code}",
                code,
                502,
            ) from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise DomainError(
                "GitHub API is unavailable", "github_api_unavailable", 502
            ) from error
