#!/usr/bin/env python3
"""Merge a chai-bot PR if all it does is add one org member to peribolos.yaml.

Runs under pull_request_target, so everything from the PR is untrusted data.
Anything that is not exactly the expected change stays open for an admin.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BOT_ID = 273475629  # redhat-chai-bot
CONFIG = "peribolos.yaml"
INVITATION_URL = "https://github.com/orgs/fullsend-day-of-learning/invitation"
MERGE_ATTEMPTS = 5
RETRY_SECONDS = 10

# GitHub logins: up to 39 alphanumerics or single hyphens, none at either end.
LOGIN = r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}"
ENTRY = re.compile(rf"      - ({LOGIN})")
HUNK = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class Rejected(Exception):
    """The PR is not an automatic membership change."""


def added_line(patch):
    """Return (1-based line number, text) of the only change in a diff patch."""
    added = []
    number = 0
    for line in patch.splitlines():
        hunk = HUNK.match(line)
        if hunk:
            number = int(hunk.group(1))
        elif line.startswith("+"):
            added.append((number, line[1:]))
            number += 1
        elif line.startswith("-"):
            raise Rejected(f"it removes a line from {CONFIG}")
        elif line.startswith(" "):
            number += 1
    if len(added) != 1:
        raise Rejected(f"it must add exactly one line to {CONFIG}")
    return added[0]


def section(lines, name):
    """Return (start, end) indexes of the entries under an org-level list."""
    headers = [i for i, line in enumerate(lines) if line == f"    {name}:"]
    if len(headers) != 1:
        raise Rejected(f"{CONFIG} must have exactly one {name} section")
    start = end = headers[0] + 1
    while end < len(lines) and ENTRY.fullmatch(lines[end]):
        end += 1
    return start, end


def existing_logins(text):
    """Return the lowercased admins and members in a peribolos.yaml."""
    lines = text.splitlines()
    logins = set()
    for name in ("admins", "members"):
        start, end = section(lines, name)
        logins.update(ENTRY.fullmatch(line).group(1).lower() for line in lines[start:end])
    return logins


def validate(files, head_text, main_text):
    """Return the login a PR adds, or raise Rejected.

    files is the PR's file list; head_text and main_text are peribolos.yaml at
    the PR head and on the current main.
    """
    if len(files) != 1 or files[0]["filename"] != CONFIG or files[0]["status"] != "modified":
        raise Rejected(f"it must change only {CONFIG}")

    number, text = added_line(files[0].get("patch", ""))
    entry = ENTRY.fullmatch(text)
    if not entry:
        raise Rejected("the added line is not a valid member entry")

    lines = head_text.splitlines()
    start, end = section(lines, "members")
    if not start <= number - 1 < end or lines[number - 1] != text:
        raise Rejected("the added line is not in the org members list")

    login = entry.group(1)
    if login.lower() in existing_logins(main_text):
        raise Rejected(f"{login} is already listed in {CONFIG}")
    return login


class GitHub:
    def __init__(self, token, repo):
        self.token = token
        self.repo = repo

    def request(self, method, path, body=None, raw=False):
        """Return (status, response); expected API errors are returned, not raised."""
        request = urllib.request.Request(
            f"https://api.github.com{path}",
            method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={
                "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read().decode()
                return response.status, data if raw else json.loads(data or "null")
        except urllib.error.HTTPError as error:
            if error.code in (404, 405, 409):
                return error.code, None
            raise

    def get(self, path, raw=False):
        status, data = self.request("GET", path, raw=raw)
        if status != 200:
            raise RuntimeError(f"GET {path} returned {status}")
        return data

    def config_at(self, ref):
        return self.get(f"/repos/{self.repo}/contents/{CONFIG}?ref={ref}", raw=True)

    def comment(self, number, body):
        self.request("POST", f"/repos/{self.repo}/issues/{number}/comments", {"body": body})

    def is_user(self, login):
        status, user = self.request("GET", f"/users/{urllib.parse.quote(login)}")
        return status == 200 and user["type"] == "User"

    def merge(self, number, sha, title):
        """Merge exactly sha; return whether it merged.

        405 can be transient, while GitHub recomputes mergeability or another
        merge lands. 409 means the head moved, and that push reruns this check.
        """
        body = {"sha": sha, "merge_method": "squash", "commit_title": title}
        for attempt in range(1, MERGE_ATTEMPTS + 1):
            status, _ = self.request("PUT", f"/repos/{self.repo}/pulls/{number}/merge", body)
            if status == 200:
                return True
            if status != 405 or attempt == MERGE_ATTEMPTS:
                return False
            time.sleep(RETRY_SECONDS * attempt)
        return False


def run(github, number):
    pr = github.get(f"/repos/{github.repo}/pulls/{number}")
    if pr["user"]["id"] != BOT_ID or pr["draft"] or pr["state"] != "open":
        print("Not an open, ready chai-bot PR; nothing to do.")
        return 0

    sha = pr["head"]["sha"]
    try:
        files = github.get(f"/repos/{github.repo}/pulls/{number}/files")
        login = validate(files, github.config_at(sha), github.config_at("main"))
        if not github.is_user(login):
            raise Rejected(f"{login} is not a GitHub user account")
    except Rejected as reason:
        github.comment(number, f"Not merged automatically: {reason}. An org admin needs to review this PR.")
        print(f"Rejected: {reason}", file=sys.stderr)
        return 1

    if not github.merge(number, sha, f"Add {login} to org members (#{number})"):
        github.comment(number, "Not merged automatically: GitHub refused the merge. Rebase this PR on main to retry.")
        print("Merge refused", file=sys.stderr)
        return 1

    github.comment(number, f"Merged. @{login} will get an org invitation shortly; accept it at {INVITATION_URL}")
    print(f"Merged PR {number}, adding {login}")
    return 0


def main():
    github = GitHub(os.environ["GH_TOKEN"], os.environ["REPO"])
    return run(github, int(os.environ["PR_NUMBER"]))


if __name__ == "__main__":
    sys.exit(main())
