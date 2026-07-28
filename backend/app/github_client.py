import json
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import jwt

from .errors import DomainError


class GitHubAppClient:
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
            code = (
                "github_rate_limited"
                if error.code in {403, 429} and retry_after
                else "github_api_error"
            )
            raise DomainError(
                f"GitHub API request failed with status {error.code}",
                code,
                502,
            ) from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise DomainError(
                "GitHub API is unavailable", "github_api_unavailable", 502
            ) from error
