# Org membership requests

`peribolos.yaml` is the source of truth for members of the
fullsend-day-of-learning GitHub org. A chai-bot PR that adds one member is
merged without human review, and the person then gets an org invitation.

When someone asks to join the org:

1. Use the GitHub username of the person asking. Do not add anyone else on
   their behalf, and ask for the username if you don't have it.
2. Add exactly one line to the `members` list, directly under
   `orgs.fullsend-day-of-learning`, in the form `      - username` (six spaces).
   Keep the list sorted, ignoring case.
3. Change nothing else, and open one PR per person against `main`.

Tell them to accept the invitation at
https://github.com/orgs/fullsend-day-of-learning/invitation once the PR merges.

Any other PR from chai-bot stays open for an org admin to review.
