# F1 Stats packaging

This public repository packages the upstream application and owns its release workflow. Keep the upstream application in its own repository. Repository settings, IAM and credential custody belong to daybreaker-stack; workload manifests belong to their GitOps owner.

## Organization context

Read local guidance first. Consult [Sunrise's repository map](https://github.com/daybreaker-labs/sunrise/blob/main/docs/organization/README.md) and [shared agent guidance](https://github.com/daybreaker-labs/sunrise/blob/main/docs/organization/agents.md) for cross-project architecture and organization conventions. Local implementation guidance takes precedence.

## Work tracking

Track Daybreaker work in Linear. Before creating, planning, implementing or completing a task, read the [work-tracking policy](https://github.com/daybreaker-labs/sunrise/blob/main/docs/organization/work-tracking.md). Before publishing an issue or changing its scope, require a [primary owning-repository label](https://github.com/daybreaker-labs/sunrise/blob/main/docs/organization/work-tracking.md#repository-labels). Link the Linear issue to the worktree and PR, and record verification and remaining blockers in the issue. GitHub hosts code, PRs and Renovate Dependency Dashboards.

## Checks and release boundaries

Run the checks in README.md. Keep the upstream build free of release secrets and every job on GitHub-hosted ubuntu-24.04-arm. Credential-bearing jobs use the main-only release environment. Preserve archive verification, unused-tag checks, source ancestry checks and the promotion allowlist. Check public logs for private URLs and registry-account output. Use Conventional Commits and pull requests; cloud credentials and live repository settings remain owner operations.
