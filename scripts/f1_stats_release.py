#!/usr/bin/env python3
"""Steps of the F1 Stats release workflow (.github/workflows/f1-stats-image.yml).

Standard library only, and it never runs or imports upstream code: each command
talks to GitHub or Linear with the one token its job was given.

  resolve  decide whether this run releases, and what
  promote  pin the published digest in daybreaker-gitops through a merged PR
  verify   wait for the public hostname to serve that release
  status   post the commit status
  linear   open a Linear issue for a failed release
"""

from __future__ import annotations

import base64
import http
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from email.message import Message

GITOPS_REPO = "daybreaker-labs/daybreaker-gitops"
DEPLOYMENT_PATH = "components/f1-stats/base/deployment.yaml"
MIGRATE_PATH = "components/f1-stats/base/migrate-job.yaml"
# Where each manifest pins the image, so an unexpected layout stops the release.
EXPECTED_IMAGE_PINS = {DEPLOYMENT_PATH: 2, MIGRATE_PATH: 1}

STATUS_CONTEXT = "daybreaker/f1-stats-release"
UPSTREAM_ANNOTATION = "daybreaker.cloud/upstream-sha"
PACKAGING_ANNOTATION = "daybreaker.cloud/packaging-sha"
PACKAGING_PATH = "images/f1-stats"
PUBLIC_URL = "https://f1.vitorvasconcellos.com.br"

REGISTRY_IMAGE = "fra.ocir.io/frsgxpf5mpny/f1-stats"
IMAGE_RE = re.compile(re.escape(REGISTRY_IMAGE) + r"@sha256:[0-9a-f]{64}")
ANNOTATION_RE = re.compile(r'^(\s*)(daybreaker\.cloud/(?:upstream|packaging)-sha): "[0-9a-f]{40}"$')
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SUFFIX_RE = re.compile(r"^-[a-z0-9][a-z0-9.]{0,15}$")

USER_AGENT = "daybreaker-f1-stats-release"
# Actions write cannot be limited to one input, and several Apps in this
# organization hold it, so any App identity may only dispatch auto. The OKE
# CronJob is the one that does, as daybreaker-renovate-dispatch[bot].
BOT_SUFFIX = "[bot]"


class ReleaseError(Exception):
    pass


def status_description(word: str, packaging_sha: str) -> str:
    return f"{word}; packaging {packaging_sha[:7]}"


def already_attempted(description: str | None, packaging_sha: str) -> bool:
    return bool(description) and f"packaging {packaging_sha[:7]}" in description


def release_tag(upstream_sha: str, packaging_sha: str, suffix: str = "") -> str:
    if suffix and not SUFFIX_RE.match(suffix):
        raise ReleaseError("tag_suffix must match ^-[a-z0-9][a-z0-9.]{0,15}$")
    return f"{upstream_sha[:7]}-{packaging_sha[:7]}{suffix}"


def read_annotation(manifest: str, name: str) -> str | None:
    match = re.search(rf'^\s*{re.escape(name)}: "([0-9a-f]{{40}})"$', manifest, re.MULTILINE)
    return match.group(1) if match else None


def decide_scheduled(  # noqa: PLR0913, PLR0917 - called with keywords from one state snapshot
    switch: str,
    head: str,
    packaging: str,
    deployed_head: str | None,
    deployed_packaging: str | None,
    status: str | None,
) -> tuple[bool, str]:
    """Decide whether a scheduled poll releases.

    Comparing state, rather than reacting to push events, means a dropped
    queued run cannot lose a packaging change.
    """
    if switch != "true":
        return False, "F1_STATS_AUTO_DEPLOY is not true"
    if (head, packaging) == (deployed_head, deployed_packaging):
        return False, "already deployed"
    # A failed release is not retried on every poll; a new commit or a manual
    # dispatch is what tries again.
    if already_attempted(status, packaging):
        return False, "already attempted"
    return True, "new commit or packaging"


def check_auto_inputs(upstream_sha: str, tag_suffix: str, *, publish: bool, deploy: bool, ref: str) -> None:
    """Reject inputs on an auto dispatch, which decides everything from state.

    A named commit in the pending slot of the concurrency group could lose a
    release if replaced.
    """
    if upstream_sha or tag_suffix or publish or deploy:
        raise ReleaseError("auto takes no other input")
    if ref != "refs/heads/main":
        raise ReleaseError("only main publishes")


def require_on_upstream_main(upstream: str, sha: str, token: str) -> None:
    """Require the commit to be on upstream main.

    GitHub serves any commit in a fork network through the upstream repository,
    so a fork-only commit fetches like a real one. Comparing against main proves
    ancestry without running anything from that commit.
    """
    if not SHA_RE.match(sha):
        raise ReleaseError("upstream_sha must be a full lowercase commit")
    try:
        status = github(f"repos/{upstream}/compare/{sha}...main", token)["status"]
    except urllib.error.HTTPError as error:
        if error.code == http.HTTPStatus.NOT_FOUND:
            raise ReleaseError(f"{sha} is not on {upstream} main") from None
        raise
    if status not in ("ahead", "identical"):
        raise ReleaseError(f"{sha} is not on {upstream} main")


def rewrite_manifest(path: str, text: str, digest: str, upstream_sha: str, packaging_sha: str) -> str:
    if not DIGEST_RE.match(digest):
        raise ReleaseError(f"not an image digest: {digest!r}")
    for value in (upstream_sha, packaging_sha):
        if not SHA_RE.match(value):
            raise ReleaseError(f"not a full commit: {value!r}")
    pins = len(IMAGE_RE.findall(text))
    if pins != EXPECTED_IMAGE_PINS[path]:
        raise ReleaseError(f"{path} has {pins} image pins, expected {EXPECTED_IMAGE_PINS[path]}")
    image = f"{REGISTRY_IMAGE}@{digest}"
    updated = IMAGE_RE.sub(image, text)
    if path == DEPLOYMENT_PATH:
        for name, value in (
            (UPSTREAM_ANNOTATION, upstream_sha),
            (PACKAGING_ANNOTATION, packaging_sha),
        ):
            updated, count = re.subn(
                rf'^(\s*{re.escape(name)}: )"[0-9a-f]{{40}}"$',
                rf'\g<1>"{value}"',
                updated,
                flags=re.MULTILINE,
            )
            if count != 1:
                raise ReleaseError(f"{path} has {count} {name} annotations, expected 1")
    check_only_pins_changed(text, updated)
    return updated


def check_only_pins_changed(old: str, new: str) -> None:
    """Guard what an unattended merge may change.

    Only image pins and the two release annotations may change, and nothing
    else on any line.
    """
    old_lines, new_lines = old.split("\n"), new.split("\n")
    if len(old_lines) != len(new_lines):
        raise ReleaseError("a release must not add or remove lines")
    for before, after in zip(old_lines, new_lines, strict=False):
        if before == after:
            continue
        if IMAGE_RE.sub("", before) == IMAGE_RE.sub("", after) and IMAGE_RE.search(after):
            continue
        a, b = ANNOTATION_RE.match(before), ANNOTATION_RE.match(after)
        if a and b and a.groups() == b.groups():
            continue
        raise ReleaseError("a release may only change image pins and release annotations")


def wait_for_promotion(number: int, head: str, token: str) -> None:
    """The private GitOps merger checks and merges the exact promotion head."""
    deadline = time.monotonic() + int(env("CHECK_TIMEOUT_SECONDS", "900"))
    while True:
        pull = github(f"repos/{GITOPS_REPO}/pulls/{number}", token)
        if pull["head"]["sha"] != head:
            raise ReleaseError("promotion branch changed while waiting for merge")
        if pull["merged"]:
            return
        if pull["state"] != "open":
            raise ReleaseError("promotion pull request closed without merging")
        if time.monotonic() > deadline:
            raise ReleaseError("trusted GitOps merger did not finish")
        time.sleep(15)


def request(
    url: str,
    token: str | None = None,
    method: str = "GET",
    body: object = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Message | dict[str, str], bytes]:
    all_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    if token:
        all_headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        all_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=all_headers)  # noqa: S310 - fixed https or loopback URL
    with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310 - fixed https or loopback URL
        payload = response.read()
        return response.status, response.headers, payload


def github(path: str, token: str, method: str = "GET", body: object = None) -> Any:
    _, _, payload = request(
        f"https://api.github.com/{path}",
        token,
        method,
        body,
        {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
    )
    return json.loads(payload) if payload else None


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise ReleaseError(f"{name} is not set")
    return value


def write_outputs(**values: str) -> None:
    with Path(env("GITHUB_OUTPUT")).open("a", encoding="utf-8") as output:
        output.writelines(f"{key}={value}\n" for key, value in values.items())


def fetch_file(repo: str, path: str, token: str, ref: str = "main") -> tuple[str, str]:
    data = github(f"repos/{repo}/contents/{path}?ref={ref}", token)
    return base64.b64decode(data["content"]).decode(), data["sha"]


def latest_status(repo: str, sha: str, token: str) -> str | None:
    for status in github(f"repos/{repo}/commits/{sha}/statuses?per_page=100", token):
        if status["context"] == STATUS_CONTEXT:
            return status["description"]
    return None


def resolve() -> None:
    event = env("GITHUB_EVENT_NAME")
    token = env("GITHUB_TOKEN")
    upstream = env("UPSTREAM_REPO")
    packaging_repo = env("GITHUB_REPOSITORY")
    ref = env("GITHUB_REF")
    packaging = github(
        f"repos/{packaging_repo}/commits?sha={env('GITHUB_SHA')}&path={PACKAGING_PATH}&per_page=1", token
    )[0]["sha"]
    auto = event == "workflow_dispatch" and env("INPUT_AUTO", "false") == "true"
    if auto:
        check_auto_inputs(
            env("INPUT_UPSTREAM_SHA", ""),
            env("INPUT_TAG_SUFFIX", ""),
            publish=env("INPUT_PUBLISH", "false") == "true",
            deploy=env("INPUT_DEPLOY", "false") == "true",
            ref=ref,
        )
    if event == "workflow_dispatch" and not auto:
        # A re-run keeps the original actor, so the one who re-ran counts too.
        actors = (env("GITHUB_ACTOR", ""), env("GITHUB_TRIGGERING_ACTOR", ""))
        if any(actor.endswith(BOT_SUFFIX) for actor in actors):
            raise ReleaseError("an App identity may only dispatch auto")
        sha = env("INPUT_UPSTREAM_SHA", "")
        if sha:
            require_on_upstream_main(upstream, sha, token)
        else:
            sha = github(f"repos/{upstream}/commits/main", token)["sha"]
        publish = env("INPUT_PUBLISH", "false") == "true"
        deploy = env("INPUT_DEPLOY", "false") == "true"
        if deploy and not publish:
            raise ReleaseError("deploy needs publish")
        if publish and ref != "refs/heads/main":
            raise ReleaseError("only main publishes")
        run, reason = True, "manual dispatch"
    elif event == "schedule" or auto:
        sha = github(f"repos/{upstream}/commits/main", token)["sha"]
        switch = env("AUTO_DEPLOY", "false")
        deployed_head = deployed_packaging = None
        if switch == "true":
            manifest, _ = fetch_file(GITOPS_REPO, DEPLOYMENT_PATH, env("GITOPS_TOKEN"))
            deployed_head = read_annotation(manifest, UPSTREAM_ANNOTATION)
            deployed_packaging = read_annotation(manifest, PACKAGING_ANNOTATION)
        status = latest_status(upstream, sha, token)
        run, reason = decide_scheduled(switch, sha, packaging, deployed_head, deployed_packaging, status)
        publish = deploy = run
    else:
        raise ReleaseError(f"unexpected event {event}")
    if not SHA_RE.match(sha):
        raise ReleaseError("upstream_sha must be a full lowercase commit")
    print(f"run={run} ({reason}); upstream {sha}, packaging {packaging}")
    write_outputs(
        run=str(run).lower(),
        publish=str(publish).lower(),
        deploy=str(deploy).lower(),
        upstream_sha=sha,
        packaging_sha=packaging,
        tag=release_tag(sha, packaging, env("INPUT_TAG_SUFFIX", "")),
    )


def promote() -> None:
    token = env("GITOPS_TOKEN")
    digest, tag = env("DIGEST"), env("TAG")
    upstream_sha, packaging_sha = env("UPSTREAM_SHA"), env("PACKAGING_SHA")
    branch = f"f1-stats-promotion/{tag}"
    base = github(f"repos/{GITOPS_REPO}/git/ref/heads/main", token)["object"]["sha"]
    github(
        f"repos/{GITOPS_REPO}/git/refs",
        token,
        "POST",
        {"ref": f"refs/heads/{branch}", "sha": base},
    )
    for path in EXPECTED_IMAGE_PINS:
        text, blob = fetch_file(GITOPS_REPO, path, token, base)
        updated = rewrite_manifest(path, text, digest, upstream_sha, packaging_sha)
        # Commits made through this API are signed by GitHub for the App.
        github(
            f"repos/{GITOPS_REPO}/contents/{path}",
            token,
            "PUT",
            {
                "message": f"chore(f1-stats): release {tag}",
                "content": base64.b64encode(updated.encode()).decode(),
                "sha": blob,
                "branch": branch,
            },
        )
    compare = github(f"repos/{GITOPS_REPO}/compare/{base}...{branch}", token)
    changed = {item["filename"] for item in compare["files"]}
    if changed != set(EXPECTED_IMAGE_PINS):
        raise ReleaseError(f"unexpected files in the release: {sorted(changed)}")
    head = github(f"repos/{GITOPS_REPO}/git/ref/heads/{branch}", token)["object"]["sha"]
    pull = github(
        f"repos/{GITOPS_REPO}/pulls",
        token,
        "POST",
        {
            "title": f"chore(f1-stats): release {tag}",
            "head": branch,
            "base": "main",
            "body": (
                f"Automatic release of `{env('UPSTREAM_REPO')}@{upstream_sha}`, "
                f"packaged from `{env('GITHUB_REPOSITORY')}` at `{packaging_sha}`.\n\n"
                f"Image digest: `{digest}`\n\nRun: {env('RUN_URL')}"
            ),
        },
    )
    number = pull["number"]
    print("opened promotion pull request")
    wait_for_promotion(number, head, token)
    print("merged promotion pull request")
    write_outputs(pull_url=pull["html_url"])


def public_response(path: str) -> tuple[int, Message | dict[str, str], bytes]:
    # The query keeps Cloudflare from answering with a copy from an earlier run.
    url = f"{PUBLIC_URL}{path}?release={env('GITHUB_RUN_ID')}"
    try:
        return request(url)
    except urllib.error.HTTPError as error:
        return error.code, error.headers, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, {}, b""


def verify() -> None:
    upstream_sha, packaging_sha = env("UPSTREAM_SHA"), env("PACKAGING_SHA")
    deadline = time.monotonic() + int(env("VERIFY_TIMEOUT_SECONDS", "900"))
    while True:
        status, headers, _ = public_response("/healthz")
        if (
            status == http.HTTPStatus.OK
            and headers.get("X-F1-Revision") == upstream_sha
            and headers.get("X-F1-Packaging") == packaging_sha
        ):
            break
        if time.monotonic() > deadline:
            raise ReleaseError("the public hostname did not serve this release in time")
        time.sleep(15)
    failures = []
    for path in ("/", "/users/login"):
        status, _, _ = public_response(path)
        print(f"{path} {status}")
        if status != http.HTTPStatus.OK:
            failures.append(f"{path} returned {status}")
    if failures:
        raise ReleaseError("; ".join(failures))
    print(f"serving {upstream_sha}")


def post_status() -> None:
    state = env("STATE")
    word = {"pending": "releasing", "success": "live", "failure": "failed"}[state]
    github(
        f"repos/{env('UPSTREAM_REPO')}/statuses/{env('UPSTREAM_SHA')}",
        env("STATUS_TOKEN"),
        "POST",
        {
            "state": state,
            "context": STATUS_CONTEXT,
            "description": status_description(word, env("PACKAGING_SHA")),
            "target_url": env("RUN_URL"),
        },
    )
    print(f"status {state}")


def linear(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    _, _, payload = request(
        "https://api.linear.app/graphql",
        method="POST",
        body={"query": query, "variables": variables},
        headers={"Authorization": env("LINEAR_API_KEY")},
    )
    result = json.loads(payload)
    if result.get("errors"):
        raise ReleaseError("Linear refused the request")
    return result["data"]


def create_linear_issue(title: str, description: str) -> None:
    query = "mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { url } } }"
    created = linear(
        query,
        {
            "input": {
                "teamId": env("LINEAR_TEAM_ID"),
                "projectId": env("LINEAR_PROJECT_ID"),
                "labelIds": [env("LINEAR_LABEL_ID")],
                "title": title,
                "description": description,
            }
        },
    )["issueCreate"]
    if not created["success"]:
        raise ReleaseError("Linear refused the issue")
    print("opened failure issue")


def open_linear_issue() -> None:
    sha = env("UPSTREAM_SHA")
    create_linear_issue(
        f"F1 Stats release failed for {sha[:7]}",
        (
            f"The automatic release of `{env('UPSTREAM_REPO')}@{sha}` "
            f"(packaging `{env('PACKAGING_SHA')}`) failed.\n\n"
            f"Run: {env('RUN_URL')}\n\nFailed jobs: {env('FAILED_JOBS')}\n\n"
            "Production keeps its last good digest, but a migration may already have run. "
            "A new commit or a manual dispatch with a `tag_suffix` tries again."
        ),
    )


COMMANDS = {
    "resolve": resolve,
    "promote": promote,
    "verify": verify,
    "status": post_status,
    "linear": open_linear_issue,
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in COMMANDS:  # noqa: PLR2004 - program name and one command
        print(f"usage: {argv[0]} {{{','.join(COMMANDS)}}}", file=sys.stderr)
        return 2
    try:
        COMMANDS[argv[1]]()
    except ReleaseError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except urllib.error.HTTPError as error:
        # The response body can echo request details, so only the code is shown.
        print(f"error: HTTP request returned {error.code}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
