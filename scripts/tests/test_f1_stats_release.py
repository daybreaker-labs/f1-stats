import email.message
import io
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import f1_stats_release as release

OLD = "sha256:" + "a" * 64
NEW = "sha256:" + "b" * 64
UP = "1" * 40
PKG = "2" * 40
IMAGE = "fra.ocir.io/frsgxpf5mpny/f1-stats@"

DEPLOYMENT = f"""metadata:
  annotations:
    daybreaker.cloud/upstream-sha: "{"3" * 40}"
    daybreaker.cloud/packaging-sha: "{"4" * 40}"
spec:
  initContainers:
    - image: {IMAGE}{OLD}
  containers:
    - image: {IMAGE}{OLD}
"""
MIGRATE = f"""spec:
  containers:
    - image: {IMAGE}{OLD}
      args: [php, artisan, migrate, --force]
"""


class DecideScheduled(unittest.TestCase):
    def decide(self, **overrides):
        values = {
            "switch": "true",
            "head": UP,
            "packaging": PKG,
            "deployed_head": "3" * 40,
            "deployed_packaging": PKG,
            "status": None,
        }
        values.update(overrides)
        return release.decide_scheduled(**values)[0]

    def test_new_commit_releases(self):
        self.assertTrue(self.decide())

    def test_new_packaging_releases_the_same_commit(self):
        self.assertTrue(self.decide(deployed_head=UP, deployed_packaging="4" * 40))

    def test_switch_off_never_releases(self):
        self.assertFalse(self.decide(switch="false"))
        self.assertFalse(self.decide(switch=""))

    def test_deployed_state_does_nothing(self):
        self.assertFalse(self.decide(deployed_head=UP))

    def test_failed_attempt_is_not_retried(self):
        status = release.status_description("failed", PKG)
        self.assertFalse(self.decide(status=status))

    def test_failed_commit_retries_with_new_packaging(self):
        status = release.status_description("failed", "9" * 40)
        self.assertTrue(self.decide(status=status))

    def test_missing_annotations_release(self):
        self.assertTrue(self.decide(deployed_head=None, deployed_packaging=None))


DISPATCHER = "daybreaker-renovate-dispatch[bot]"


class FakeGitHub:
    """Answer the calls resolve makes.

    Anything else fails the test, so a code path that would touch a status, a
    build or a tag cannot pass unnoticed.
    """

    def __init__(self, compare="ahead", main=UP, statuses=(), manifest=None):
        self.compare, self.main, self.statuses = compare, main, list(statuses)
        self.manifest = manifest if manifest is not None else DEPLOYMENT
        self.calls = []

    def __call__(self, path, token, method="GET", body=None):
        self.calls.append((method, path, token))
        if method != "GET":
            raise AssertionError(f"resolve must only read: {method} {path}")
        if "/compare/" in path:
            if isinstance(self.compare, Exception):
                raise self.compare
            return {"status": self.compare}
        if "/commits?sha=" in path:
            return [{"sha": PKG}]
        if path.endswith("/commits/main"):
            return {"sha": self.main}
        if path.endswith("/statuses?per_page=100"):
            return self.statuses
        raise AssertionError(f"unexpected call {path}")


class Resolve(unittest.TestCase):
    def resolve(self, fake, event="workflow_dispatch", **env_values):
        values = {
            "GITHUB_EVENT_NAME": event,
            "GITHUB_TOKEN": "t",
            "GITOPS_TOKEN": "g",
            "UPSTREAM_REPO": "up/repo",
            "GITHUB_REPOSITORY": "stack/repo",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": PKG,
            "AUTO_DEPLOY": "true",
            "INPUT_AUTO": "false",
            "INPUT_UPSTREAM_SHA": "",
            "INPUT_TAG_SUFFIX": "",
            "INPUT_PUBLISH": "false",
            "INPUT_DEPLOY": "false",
        }
        values.update(env_values)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out"
            values["GITHUB_OUTPUT"] = str(output)
            with (
                mock.patch.dict(os.environ, values, clear=True),
                mock.patch.object(release, "github", fake),
                mock.patch.object(release, "fetch_file", lambda *a, **k: (fake.manifest, "blob")),  # noqa: PT008 - reads fake.manifest at call time
                mock.patch("sys.stdout", io.StringIO()),
            ):
                release.resolve()
            return dict(line.split("=", 1) for line in output.read_text().splitlines())

    def live(self):
        return DEPLOYMENT.replace("3" * 40, UP).replace("4" * 40, PKG)

    def test_auto_on_the_live_commit_builds_nothing_and_posts_nothing(self):
        fake = FakeGitHub(manifest=self.live())
        out = self.resolve(fake, INPUT_AUTO="true")
        self.assertEqual((out["run"], out["publish"], out["deploy"]), ("false", "false", "false"))
        self.assertTrue(all(method == "GET" for method, _, _ in fake.calls))

    def test_auto_on_a_new_commit_releases_upstream_main(self):
        out = self.resolve(FakeGitHub(), INPUT_AUTO="true")
        self.assertEqual((out["run"], out["deploy"], out["upstream_sha"]), ("true", "true", UP))

    def test_auto_with_the_switch_off_picks_nothing_up(self):
        fake = FakeGitHub()
        out = self.resolve(fake, INPUT_AUTO="true", AUTO_DEPLOY="false")
        self.assertEqual((out["run"], out["deploy"]), ("false", "false"))

    def test_auto_does_not_retry_an_attempted_release(self):
        statuses = [
            {
                "context": release.STATUS_CONTEXT,
                "description": release.status_description("failed", PKG),
            }
        ]
        out = self.resolve(FakeGitHub(statuses=statuses), INPUT_AUTO="true")
        self.assertEqual(out["run"], "false")

    def test_auto_refuses_every_other_input(self):
        for overrides in (
            {"INPUT_UPSTREAM_SHA": UP},
            {"INPUT_TAG_SUFFIX": "-2"},
            {"INPUT_PUBLISH": "true"},
            {"INPUT_DEPLOY": "true"},
            {"GITHUB_REF": "refs/heads/branch"},
        ):
            fake = FakeGitHub()
            with self.subTest(overrides), self.assertRaises(release.ReleaseError):
                self.resolve(fake, INPUT_AUTO="true", **overrides)
            self.assertEqual(fake.calls[1:], [])

    def test_manual_dispatch_still_ignores_the_switch(self):
        out = self.resolve(FakeGitHub(), AUTO_DEPLOY="false", INPUT_PUBLISH="true", INPUT_DEPLOY="true")
        self.assertEqual((out["run"], out["deploy"]), ("true", "true"))

    def test_dispatcher_identity_may_only_dispatch_auto(self):
        fake = FakeGitHub()
        with self.assertRaises(release.ReleaseError):
            self.resolve(
                fake,
                GITHUB_ACTOR=DISPATCHER,
                INPUT_PUBLISH="true",
                INPUT_DEPLOY="true",
            )
        self.assertFalse([c for c in fake.calls if "/compare/" in c[1]])
        with self.assertRaises(release.ReleaseError):
            self.resolve(
                FakeGitHub(),
                GITHUB_ACTOR="person",
                GITHUB_TRIGGERING_ACTOR=DISPATCHER,
            )
        out = self.resolve(FakeGitHub(), GITHUB_ACTOR=DISPATCHER, INPUT_AUTO="true")
        self.assertEqual(out["upstream_sha"], UP)

    def test_every_app_identity_may_only_dispatch_auto(self):
        for actor in ("some-other-app[bot]", "daybreaker-f1-dispatch[bot]"):
            with self.subTest(actor), self.assertRaises(release.ReleaseError):
                self.resolve(FakeGitHub(), GITHUB_ACTOR=actor)

    def test_commit_on_upstream_main_is_accepted(self):
        for compare in ("ahead", "identical"):
            out = self.resolve(FakeGitHub(compare=compare), INPUT_UPSTREAM_SHA="5" * 40)
            self.assertEqual(out["upstream_sha"], "5" * 40)

    def test_fork_only_commit_is_rejected_before_anything_runs(self):
        for compare in ("diverged", "behind"):
            with self.subTest(compare), self.assertRaises(release.ReleaseError):
                self.resolve(FakeGitHub(compare=compare), INPUT_UPSTREAM_SHA="5" * 40)

    def test_commit_the_comparison_cannot_find_is_rejected(self):
        missing = urllib.error.HTTPError("u", 404, "nf", email.message.Message(), None)
        with self.assertRaises(release.ReleaseError):
            self.resolve(FakeGitHub(compare=missing), INPUT_UPSTREAM_SHA="5" * 40)

    def test_comparison_outage_is_not_read_as_a_verdict(self):
        outage = urllib.error.HTTPError("u", 503, "x", email.message.Message(), None)
        with self.assertRaises(urllib.error.HTTPError):
            self.resolve(FakeGitHub(compare=outage), INPUT_UPSTREAM_SHA="5" * 40)

    def test_malformed_commit_never_reaches_the_api(self):
        fake = FakeGitHub()
        with self.assertRaises(release.ReleaseError):
            self.resolve(fake, INPUT_UPSTREAM_SHA="main/../../x")
        self.assertFalse([c for c in fake.calls if "/compare/" in c[1]])


class WorkflowGuards(unittest.TestCase):
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/f1-stats-image.yml").read_text()

    def test_auto_dispatch_follows_the_switch_before_any_token(self):
        self.assertIn(
            "if: (github.event_name == 'workflow_dispatch' && !inputs.auto) || vars.F1_STATS_AUTO_DEPLOY == 'true'",
            self.workflow,
        )

    def test_registry_mask_precedes_image_environment(self):
        publish = re.search(r"(?ms)^  publish:\n.*?(?=^  \S|\Z)", self.workflow).group()
        self.assertNotIn("IMAGE:", publish.split("    steps:", 1)[0])
        section = publish.split("      - name: Mask registry account in command output\n", 1)[1]
        program = textwrap.dedent(section.split("        run: |\n", 1)[1].split("\n      - ", 1)[0])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "env"
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", program],
                cwd=Path(__file__).resolve().parents[2],
                env={**os.environ, "GITHUB_ENV": str(output)},
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            namespace = release.REGISTRY_IMAGE.split("/")[1]
            self.assertEqual(result.stdout, f"::add-mask::{namespace}\n")
            self.assertEqual(output.read_text(), f"IMAGE={release.REGISTRY_IMAGE}\n")

    def test_auto_dispatch_reads_the_deployed_release(self):
        self.assertIn("if: github.event_name == 'schedule' || inputs.auto", self.workflow)

    def test_publish_reads_machine_json_with_old_buildx(self):
        section = self.workflow.split("      - name: Publish an unused tag and verify the index\n", 1)[1]
        program = textwrap.dedent(section.split("        run: |\n", 1)[1].split("\n      - ", 1)[0])
        docker = r"""
        docker() {
          if [[ "$*" == 'buildx imagetools inspect '* ]]; then
            if [[ " $* " == *' --raw '* ]]; then
              printf '{"manifests":[{"digest":"%s","platform":{"os":"linux","architecture":"arm64"}}]}\n' "$ARM_DIGEST"
            elif [[ " $* " == *' --format '* ]]; then
              format="${!#}"
              value="$DIGEST"
              if [[ "$4" == *-arm64 ]]; then value="$ARM_DIGEST"; fi
              if [[ "$format" == '{{.Manifest'* ]]; then
                printf 'Name: image\nMediaType: index\nDigest: %s\n' "$value"
              else
                printf '{"digest":"%s","mediaType":"application/vnd.oci.image.index.v1+json"}\n' "$value"
              fi
            else
              echo 'not found' >&2
              return 1
            fi
          elif [[ "$*" == 'tag '* || "$*" == 'push '* || "$*" == 'buildx imagetools create '* ]]; then
            return 0
          else
            return 1
          fi
        }
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = {
                **os.environ,
                "IMAGE": IMAGE.removesuffix("@"),
                "TAG": "1111111-2222222",
                "DIGEST": NEW,
                "ARM_DIGEST": OLD,
                "UPSTREAM_SHA": UP,
                "PACKAGING_SHA": PKG,
                "GITHUB_OUTPUT": str(root / "output"),
                "GITHUB_STEP_SUMMARY": str(root / "summary"),
            }
            result = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", textwrap.dedent(docker) + program],
                cwd=root,
                env=values,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "output").read_text(), "digest=" + NEW + "\n")
            self.assertNotIn("frsgxpf5mpny", result.stdout + (root / "summary").read_text())

    def test_every_release_job_uses_the_public_arm_runner(self):
        runners = re.findall(r"(?m)^    runs-on: (.+)$", self.workflow)
        self.assertEqual(runners, ["ubuntu-24.04-arm"] * 6)

    def test_credentials_are_main_environment_only_and_absent_from_build(self):
        for job in ["resolve", "publish", "promote", "report"]:
            section = re.search(rf"(?ms)^  {job}:\n.*?(?=^  \S|\Z)", self.workflow)
            self.assertIsNotNone(section)
            self.assertIn("    environment: release", section.group())
        build = re.search(r"(?ms)^  build:\n.*?(?=^  \S|\Z)", self.workflow).group()
        self.assertNotIn("secrets.", build)
        self.assertNotIn("environment:", build)
        self.assertIn("github.repository == 'daybreaker-labs/f1-stats'", self.workflow)

    def test_a_tick_cannot_cancel_a_running_release(self):
        self.assertIn("cancel-in-progress: false", self.workflow)


class RewriteManifest(unittest.TestCase):
    def test_deployment_changes_pins_and_annotations(self):
        out = release.rewrite_manifest(release.DEPLOYMENT_PATH, DEPLOYMENT, NEW, UP, PKG)
        self.assertEqual(out.count(NEW), 2)
        self.assertNotIn(OLD, out)
        self.assertEqual(release.read_annotation(out, release.UPSTREAM_ANNOTATION), UP)
        self.assertEqual(release.read_annotation(out, release.PACKAGING_ANNOTATION), PKG)

    def test_migrate_job_changes_only_its_pin(self):
        out = release.rewrite_manifest(release.MIGRATE_PATH, MIGRATE, NEW, UP, PKG)
        self.assertEqual(out, MIGRATE.replace(OLD, NEW))

    def test_unexpected_pin_count_stops_the_release(self):
        with self.assertRaises(release.ReleaseError):
            release.rewrite_manifest(release.MIGRATE_PATH, DEPLOYMENT, NEW, UP, PKG)

    def test_missing_annotation_stops_the_release(self):
        text = DEPLOYMENT.replace("packaging-sha", "other")
        with self.assertRaises(release.ReleaseError):
            release.rewrite_manifest(release.DEPLOYMENT_PATH, text, NEW, UP, PKG)

    def test_bad_values_stop_the_release(self):
        with self.assertRaises(release.ReleaseError):
            release.rewrite_manifest(release.MIGRATE_PATH, MIGRATE, "latest", UP, PKG)
        with self.assertRaises(release.ReleaseError):
            release.rewrite_manifest(release.MIGRATE_PATH, MIGRATE, NEW, "main", PKG)

    def test_guard_refuses_any_other_change(self):
        pinned = MIGRATE.replace(OLD, NEW)
        for changed in (
            pinned.replace("--force", "--seed"),
            pinned.replace(IMAGE, "evil.example/f1-stats@"),
            pinned + "extra: line\n",
        ):
            with self.assertRaises(release.ReleaseError):
                release.check_only_pins_changed(MIGRATE, changed)


class CheckResults(unittest.TestCase):
    def run_(self, id_, name, status="completed", conclusion="success"):
        return {"id": id_, "name": name, "status": status, "conclusion": conclusion}

    def test_waits_for_checks_not_yet_reported(self):
        self.assertEqual(release.check_results([self.run_(1, "zizmor")]), "pending")

    def test_waits_for_other_running_checks(self):
        runs = [
            self.run_(1, "zizmor"),
            self.run_(2, "root-render"),
            self.run_(3, "actionlint", "in_progress", None),
        ]
        self.assertEqual(release.check_results(runs), "pending")

    def test_all_passed(self):
        runs = [self.run_(1, "zizmor"), self.run_(2, "root-render")]
        self.assertEqual(release.check_results(runs), "success")

    def test_any_failure_fails(self):
        runs = [self.run_(1, "zizmor"), self.run_(2, "actionlint", conclusion="failure")]
        self.assertEqual(release.check_results(runs), "failure")

    def test_rerun_replaces_an_earlier_failure(self):
        runs = [
            self.run_(1, "zizmor", conclusion="failure"),
            self.run_(2, "zizmor"),
            self.run_(3, "root-render"),
        ]
        self.assertEqual(release.check_results(runs), "success")

    def test_skipped_checks_do_not_block(self):
        runs = [
            self.run_(1, "zizmor"),
            self.run_(2, "root-render"),
            self.run_(3, "otel", conclusion="skipped"),
        ]
        self.assertEqual(release.check_results(runs), "success")


class PublicOutput(unittest.TestCase):
    def test_status_links_to_the_public_run(self):
        run_url = "https://github.com/daybreaker-labs/f1-stats/actions/runs/123"
        values = {
            "STATE": "success",
            "UPSTREAM_REPO": "up/repo",
            "UPSTREAM_SHA": UP,
            "STATUS_TOKEN": "status-token",
            "PACKAGING_SHA": PKG,
            "RUN_URL": run_url,
        }
        with mock.patch.dict(os.environ, values, clear=True), mock.patch.object(release, "github") as github:
            release.post_status()
        body = github.call_args.args[3]
        self.assertEqual(body["target_url"], run_url)
        self.assertEqual(body["context"], "daybreaker/f1-stats-release")

    def test_http_failure_hides_the_request_url(self):
        error = urllib.error.HTTPError("https://private.example/path", 403, "forbidden", {}, None)
        with (
            mock.patch.dict(release.COMMANDS, {"resolve": mock.Mock(side_effect=error)}),
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            self.assertEqual(release.main(["release", "resolve"]), 1)
        self.assertIn("403", stderr.getvalue())
        self.assertNotIn("private.example", stderr.getvalue())

    def test_failure_issue_logs_no_private_link(self):
        with (
            mock.patch.dict(
                os.environ, {"LINEAR_TEAM_ID": "team", "LINEAR_PROJECT_ID": "project", "LINEAR_LABEL_ID": "label"}
            ),
            mock.patch.object(
                release,
                "linear",
                return_value={"issueCreate": {"success": True, "issue": {"url": "https://private.example/issue"}}},
            ),
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            release.create_linear_issue("failure", "details")
        self.assertEqual(stdout.getvalue(), "opened failure issue\n")


class ReleaseTag(unittest.TestCase):
    def test_names_both_sources(self):
        self.assertEqual(release.release_tag(UP, PKG), "1111111-2222222")
        self.assertEqual(release.release_tag(UP, PKG, "-2"), "1111111-2222222-2")

    def test_rejects_a_bad_suffix(self):
        with self.assertRaises(release.ReleaseError):
            release.release_tag(UP, PKG, "; rm -rf /")


if __name__ == "__main__":
    unittest.main()
