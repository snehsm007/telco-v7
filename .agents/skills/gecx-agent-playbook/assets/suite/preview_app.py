#!/usr/bin/env python3
"""Create-or-find and delete per-pull-request preview apps.

Each PR gets its own throwaway app (display name `<agent>-pr-<number>`), so two
PRs never fight over one staging app. Uses SCRAPI:
`cxas_scrapi.core.apps.Apps(project_id, location).get_app_by_display_name(name)`.

Usage:
  python suite/preview_app.py resolve --project P --location L --name my-agent-pr-12
      prints the app resource name, or nothing (exit 0) if it doesn't exist
  python suite/preview_app.py --self-test

Create/update and delete use the CLI (see the Makefile `preview-up` / `preview-down`):
  cxas push --app-dir cxas_app --display-name NAME --project-id P --location L   # creates
  cxas push --app-dir cxas_app --to <resource> --create-version ...              # updates
  cxas delete --display-name NAME --project-id P --location L --force
"""

import argparse
import sys


def resolve(apps_client, name):
    app = apps_client.get_app_by_display_name(name)
    return app.name if app else ""


def self_test():
    class App:
        def __init__(self, name):
            self.name = name

    class FakeApps:
        def get_app_by_display_name(self, n):
            return App("projects/p/locations/us/apps/123") if n == "a-pr-1" else None

    assert resolve(FakeApps(), "a-pr-1") == "projects/p/locations/us/apps/123"
    assert resolve(FakeApps(), "a-pr-2") == ""
    print("OK (preview_app self-test)")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("command", nargs="?", choices=["resolve"])
    p.add_argument("--project")
    p.add_argument("--location")
    p.add_argument("--name")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    if a.self_test:
        return self_test()
    if a.command != "resolve" or not (a.project and a.location and a.name):
        p.error("usage: resolve --project P --location L --name NAME")
    from cxas_scrapi.core.apps import (
        Apps,
    )  # imported late so --self-test needs no SCRAPI

    print(resolve(Apps(project_id=a.project, location=a.location), a.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
