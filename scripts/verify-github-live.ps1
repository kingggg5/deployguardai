param(
    [string]$Repository = 'kingggg5/deployguardai',
    [string]$ApiBaseUrl = 'http://127.0.0.1:8100',
    [string]$GitHubToken = ''
)

$ErrorActionPreference = 'Stop'

if ($Repository -notmatch '^[^/\s]+/[^/\s]+$') {
    throw 'Repository must use the owner/name format.'
}

$owner, $name = $Repository.Split('/', 2)
$githubHeaders = @{
    Accept = 'application/vnd.github+json'
    'X-GitHub-Api-Version' = '2022-11-28'
    'User-Agent' = 'DeployGuard-live-verifier'
}
if ($GitHubToken.Trim()) {
    $githubHeaders.Authorization = "Bearer $($GitHubToken.Trim())"
}

function Invoke-JsonGet {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][hashtable]$Headers
    )

    Invoke-RestMethod -Method Get -Uri $Uri -Headers $Headers -TimeoutSec 20
}

$health = Invoke-JsonGet -Uri "$($ApiBaseUrl.TrimEnd('/'))/api/v1/health" -Headers @{
    Accept = 'application/json'
}
$latestCommit = $null
$repositoryData = $null
$pulls = @()
$deployments = @()
$verificationMode = 'live-read-only'

if ($GitHubToken.Trim()) {
    $repositoryData = Invoke-JsonGet -Uri "https://api.github.com/repos/$owner/$name" -Headers $githubHeaders
    $commits = @(Invoke-JsonGet -Uri "https://api.github.com/repos/$owner/$name/commits?per_page=5" -Headers $githubHeaders)
    $pulls = @(Invoke-JsonGet -Uri "https://api.github.com/repos/$owner/$name/pulls?state=open&per_page=5" -Headers $githubHeaders)
    $deployments = @(Invoke-JsonGet -Uri "https://api.github.com/repos/$owner/$name/deployments?per_page=5" -Headers $githubHeaders)
    if ($commits.Count) {
        $latestCommit = $commits[0].sha
    }
} else {
    # Git transport and the commits Atom feed are public and avoid consuming
    # the shared unauthenticated REST API quota. This remains read-only.
    $head = (& git ls-remote "https://github.com/$Repository.git" HEAD 2>$null).Split("`t")[0]
    if ($head -notmatch '^[0-9a-f]{40}$') {
        throw "Could not resolve a live Git HEAD for $Repository."
    }
    $latestCommit = $head
    $feed = Invoke-RestMethod -Method Get -Uri "https://github.com/$Repository/commits/main.atom" -Headers @{ 'User-Agent' = 'DeployGuard-live-verifier' } -TimeoutSec 20
    $repositoryData = [pscustomobject]@{ full_name = $Repository; default_branch = 'main'; visibility = 'public' }
    $verificationMode = 'live-read-only-git-transport'
}

[pscustomobject]@{
    api_status = $health.status
    api_database = $health.database
    api_data_mode = $health.data_mode
    github_repository = $repositoryData.full_name
    github_default_branch = $repositoryData.default_branch
    github_visibility = $repositoryData.visibility
    latest_commit = $latestCommit
    open_pull_requests = if ($GitHubToken.Trim()) { $pulls.Count } else { $null }
    recent_deployments = if ($GitHubToken.Trim()) { $deployments.Count } else { $null }
    verification = $verificationMode
} | ConvertTo-Json

Write-Output 'No GitHub or DeployGuard records were created or modified.'
