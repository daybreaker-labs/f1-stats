# F1 Stats packaging

Public container packaging and releases for [viniciusmelchior/f1_2022](https://github.com/viniciusmelchior/f1_2022). The application stays upstream; this repository owns the Docker image and release workflow.

The image runs PHP-FPM and nginx as an unprivileged user on port 8080. Builds target native `linux/arm64`, pin base-image digests and verify both the upstream commit and packaging revision. PR checks and release control jobs use GitHub-hosted `ubuntu-24.04-arm`. The credential-free build uses `blacksmith-4vcpu-ubuntu-2404-arm`; cold PHP builds exceed the GitHub runner timeout.

The build uses a pinned Blacksmith builder with the `f1-stats-runtime-arm64`
layer cache. A successful job commits its cache for later builds, allowing
unchanged runtime package installs to skip network downloads; the first build
is cold, and seven days without a build evicts the cache. Build logs show the
selected builder and its cache usage.

The PHP image currently omits OpenTelemetry instrumentation while authenticated
page performance is qualified; GitOps `OTEL_*` settings have no effect in this image.

## Release flow

[The release workflow](.github/workflows/f1-stats-image.yml) compares upstream `main` and the latest commit under `images/f1-stats/` with the deployed revisions. Automatic polls run only when `F1_STATS_AUTO_DEPLOY` is `true`; manual dispatch from `main` can build without publication or request publication and deployment.

1. Build and smoke-test upstream code without release secrets, then rehearse migrations against a throwaway MySQL database.
2. Pass the image archive through a GitHub artifact retained for one day to a separate publishing job, checking its SHA-256, image ID, architecture and source revision before registry login.
3. Publish an unused `<upstream sha7>-<packaging sha7>` tag and verify its image-index digest. Existing tags are never overwritten; a manual rebuild can supply a suffix.
4. Promote the digest through a reviewed GitOps change, wait for public health checks, and post `daybreaker/f1-stats-release` on the upstream commit.

The upstream commit status links to this public repository's run. A failed release opens a failure issue; a new commit or explicit manual retry starts another attempt. Promotion updates GitOps before live verification, so a verification failure can leave the new digest deployed. There is no automatic rollback, and database migrations can prevent restoring an older application image.

## Configuration

All secrets belong in the `release` environment, restricted to `main`. Only the resolve, publish, promote and report jobs reference it. The build job runs upstream code without these secrets; PR checks run tests and linters only.

| Kind | Names |
| --- | --- |
| Environment secrets | `OCIR_AUTH_TOKEN`, `F1_DEPLOY_APP_ID`, `F1_DEPLOY_APP_PRIVATE_KEY`, `F1_STATUS_APP_ID`, `F1_STATUS_APP_PRIVATE_KEY`, `LINEAR_API_KEY` |
| Repository variables | `OCIR_USERNAME`, `F1_STATS_AUTO_DEPLOY` |
| Optional upstream overrides | `F1_STATS_UPSTREAM_OWNER`, `F1_STATS_UPSTREAM_NAME` |

The registry credential is dedicated to the F1 Stats image. The dedicated
`daybreaker-f1-stats-deploy` App (ID `5611521`) uses the unchanged `F1_DEPLOY_APP_*`
secret names. GitOps restricts its branch writes to `f1-stats-promotion/**` and
requires promotions to stay under `components/f1-stats/`. The public release
opens the PR and waits up to 15 minutes for the private GitOps merger; it cannot
write `main` or merge the PR itself. That merger uses the shared deploy App from
a main-only GitOps environment, rechecks the exact head, paths and CI, and
merges. GitOps removes merged branches automatically; the release verifies public health.

The status App has access to the upstream repository. The dispatch App needs
Actions access to this repository. Infrastructure owners manage repository
settings, environment policy, App installations and credential custody separately.

## Checks

```sh
python3 -m unittest discover -s scripts/tests
actionlint
GH_TOKEN=<read-only-token> zizmor --persona=regular .
```

CI installs checksum-verified actionlint 1.7.12 and zizmor 1.30.1 and reports the required `check` job for pull requests and `main`. These tests exercise release decisions, immutable publication, promotion guards and commit status links without cloud credentials. The real build, registry publication and live deployment run through the release workflow.

Use a [Linear work item](https://linear.app/daybreaker-labs) in pull requests. Keep private operations and credentials in their owning systems; review workflow output before making it public.
