#!/usr/bin/env python3
"""Create a SLSA v1 predicate for the native release checksum manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


SUPPORTED_EVENTS = {"create", "push", "release", "workflow_dispatch"}
WORKFLOW_PATH = ".github/workflows/release.yml"
BUILD_TYPE = "https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1"


def release_provenance(
    *,
    repository: str,
    repository_id: str,
    repository_owner_id: str,
    ref: str,
    sha: str,
    event_name: str,
    run_id: str,
    run_attempt: str,
    release_tag: str,
) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must be an owner/name slug")
    if not ref.startswith("refs/"):
        raise ValueError("ref must start with refs/")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("sha must be a full lowercase Git commit SHA")
    if event_name not in SUPPORTED_EVENTS:
        raise ValueError(f"unsupported release event: {event_name}")
    for name, value in {
        "repository_id": repository_id,
        "repository_owner_id": repository_owner_id,
        "run_id": run_id,
        "run_attempt": run_attempt,
    }.items():
        if not value.isdigit():
            raise ValueError(f"{name} must be numeric")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", release_tag):
        raise ValueError("release_tag must be a three-part semantic version tag")

    repository_url = f"https://github.com/{repository}"
    external_parameters: dict[str, object] = {
        "workflow": {
            "ref": ref,
            "repository": repository_url,
            "path": WORKFLOW_PATH,
        }
    }
    if event_name == "workflow_dispatch":
        external_parameters["inputs"] = {"release_tag": release_tag}

    return {
        "buildDefinition": {
            "buildType": BUILD_TYPE,
            "externalParameters": external_parameters,
            "internalParameters": {
                "github": {
                    "event_name": event_name,
                    "repository_id": repository_id,
                    "repository_owner_id": repository_owner_id,
                }
            },
            "resolvedDependencies": [
                {
                    "uri": f"git+{repository_url}@{ref}",
                    "digest": {"gitCommit": sha},
                }
            ],
        },
        "runDetails": {
            "builder": {"id": f"{repository_url}/{WORKFLOW_PATH}@{ref}"},
            "metadata": {
                "invocationId": (
                    f"{repository_url}/actions/runs/{run_id}/attempts/{run_attempt}"
                )
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--repository-owner-id", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--release-tag", required=True)
    args = parser.parse_args()
    try:
        predicate = release_provenance(
            repository=args.repository,
            repository_id=args.repository_id,
            repository_owner_id=args.repository_owner_id,
            ref=args.ref,
            sha=args.sha,
            event_name=args.event_name,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            release_tag=args.release_tag,
        )
        args.output.write_text(
            json.dumps(predicate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
