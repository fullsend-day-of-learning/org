import unittest
from unittest import mock

import chai_bot_membership as cbm

MAIN = """orgs:
  fullsend-day-of-learning:
    admins:
      - jflowers

    members:
      - dhshah13
      - rh-hemartin
"""
HEAD = MAIN.replace("      - rh-hemartin", "      - newperson\n      - rh-hemartin")
PATCH = """@@ -6,3 +6,4 @@ orgs:
     members:
       - dhshah13
+      - newperson
       - rh-hemartin"""


def files(patch=PATCH, filename="peribolos.yaml", status="modified"):
    return [{"filename": filename, "status": status, "patch": patch}]


class Validate(unittest.TestCase):
    def rejected(self, *args):
        with self.assertRaises(cbm.Rejected) as caught:
            cbm.validate(*args)
        return str(caught.exception)

    def test_accepts_one_new_member(self):
        self.assertEqual(cbm.validate(files(), HEAD, MAIN), "newperson")

    def test_accepts_append_at_end(self):
        head = MAIN + "      - zed\n"
        patch = "@@ -7,2 +7,3 @@\n       - dhshah13\n       - rh-hemartin\n+      - zed"
        self.assertEqual(cbm.validate(files(patch), head, MAIN), "zed")

    def test_accepts_when_pr_is_behind_main(self):
        main = MAIN + "      - zed\n"
        self.assertEqual(cbm.validate(files(), HEAD, main), "newperson")

    def test_rejects_extra_file(self):
        self.assertIn("only", self.rejected(files() + files(filename="x.yml"), HEAD, MAIN))

    def test_rejects_other_file(self):
        self.assertIn("only", self.rejected(files(filename=".github/workflows/x.yml"), HEAD, MAIN))

    def test_rejects_new_or_renamed_config(self):
        self.assertIn("only", self.rejected(files(status="renamed"), HEAD, MAIN))

    def test_rejects_missing_patch(self):
        self.assertIn("exactly one", self.rejected([{"filename": "peribolos.yaml", "status": "modified"}], HEAD, MAIN))

    def test_rejects_two_additions(self):
        patch = PATCH + "\n+      - another"
        self.assertIn("exactly one", self.rejected(files(patch), HEAD, MAIN))

    def test_rejects_removal(self):
        patch = PATCH.replace("       - dhshah13", "-      - dhshah13")
        self.assertIn("removes", self.rejected(files(patch), HEAD, MAIN))

    def test_rejects_admin_addition(self):
        head = MAIN.replace("      - jflowers", "      - jflowers\n      - newperson")
        patch = "@@ -3,2 +3,3 @@\n     admins:\n       - jflowers\n+      - newperson"
        self.assertIn("members list", self.rejected(files(patch), head, MAIN))

    def test_rejects_entry_outside_any_list(self):
        head = MAIN + "\n      - newperson\n"
        patch = "@@ -8,1 +8,3 @@\n       - rh-hemartin\n \n+      - newperson"
        self.assertIn("members list", self.rejected(files(patch), head, MAIN))

    def test_rejects_invalid_entries(self):
        for text in (
            "      - bad-",
            "      - -bad",
            "      - two--hyphens",
            "      - a" * 1 + "b" * 39,
            "      - has space",
            "      - x # comment",
            "      - {a: b}",
            "     - wrongindent",
            "    admins:",
            "    has_repository_projects: true",
        ):
            patch = PATCH.replace("      - newperson", text)
            self.assertIn("valid member entry", self.rejected(files(patch), HEAD, MAIN), text)

    def test_rejects_existing_member_ignoring_case(self):
        head = MAIN.replace("      - rh-hemartin", "      - DHSHAH13\n      - rh-hemartin")
        patch = PATCH.replace("newperson", "DHSHAH13")
        self.assertIn("already listed", self.rejected(files(patch), head, MAIN))

    def test_rejects_existing_admin(self):
        head = MAIN.replace("      - rh-hemartin", "      - jflowers\n      - rh-hemartin")
        patch = PATCH.replace("newperson", "jflowers")
        self.assertIn("already listed", self.rejected(files(patch), head, MAIN))


class FakeGitHub(cbm.GitHub):
    def __init__(self, merge_statuses=(200,), author=cbm.BOT_ID, user_type="User", draft=False):
        super().__init__("token", "o/r")
        self.merge_statuses = list(merge_statuses)
        self.author = author
        self.user_type = user_type
        self.draft = draft
        self.comments = []
        self.merges = []

    def request(self, method, path, body=None, raw=False):
        if method == "PUT":
            self.merges.append(body)
            return self.merge_statuses.pop(0), None
        if method == "POST":
            self.comments.append(body["body"])
            return 201, None
        if path.endswith("/files"):
            return 200, files()
        if "ref=abc" in path:
            return 200, HEAD
        if "ref=main" in path:
            return 200, MAIN
        if path.startswith("/users/"):
            return (404, None) if self.user_type is None else (200, {"type": self.user_type})
        return 200, {"user": {"id": self.author}, "draft": self.draft, "state": "open", "head": {"sha": "abc"}}


@mock.patch.object(cbm.time, "sleep")
class Run(unittest.TestCase):
    def test_merges_the_validated_sha(self, _):
        github = FakeGitHub()
        self.assertEqual(cbm.run(github, 7), 0)
        self.assertEqual(github.merges[0]["sha"], "abc")
        self.assertEqual(github.merges[0]["commit_title"], "Add newperson to org members (#7)")
        self.assertIn(cbm.INVITATION_URL, github.comments[0])

    def test_ignores_other_authors(self, _):
        github = FakeGitHub(author=1)
        self.assertEqual(cbm.run(github, 7), 0)
        self.assertEqual((github.merges, github.comments), ([], []))

    def test_ignores_drafts(self, _):
        github = FakeGitHub(draft=True)
        self.assertEqual(cbm.run(github, 7), 0)
        self.assertEqual(github.merges, [])

    def test_rejects_unknown_user(self, _):
        github = FakeGitHub(user_type=None)
        self.assertEqual(cbm.run(github, 7), 1)
        self.assertEqual(github.merges, [])
        self.assertIn("not a GitHub user", github.comments[0])

    def test_rejects_organization(self, _):
        github = FakeGitHub(user_type="Organization")
        self.assertEqual(cbm.run(github, 7), 1)
        self.assertEqual(github.merges, [])

    def test_retries_transient_refusal(self, sleep):
        github = FakeGitHub(merge_statuses=(405, 405, 200))
        self.assertEqual(cbm.run(github, 7), 0)
        self.assertEqual(sleep.call_count, 2)

    def test_gives_up_when_never_mergeable(self, _):
        github = FakeGitHub(merge_statuses=(405,) * cbm.MERGE_ATTEMPTS)
        self.assertEqual(cbm.run(github, 7), 1)
        self.assertIn("Rebase", github.comments[0])

    def test_does_not_retry_when_head_moved(self, sleep):
        github = FakeGitHub(merge_statuses=(409,))
        self.assertEqual(cbm.run(github, 7), 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
