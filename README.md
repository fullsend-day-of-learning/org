# org

Membership of the fullsend-day-of-learning GitHub org, managed with
[peribolos](https://docs.prow.k8s.io/docs/components/cli-tools/peribolos/).

## Joining

Red Hat employees: message chai-bot on Slack and ask to be added to the
`fullsend-day-of-learning` GitHub org, giving your GitHub username. Accept the
invitation at https://github.com/orgs/fullsend-day-of-learning/invitation.

## How it works

1. chai-bot opens a PR adding one line to `members` in `peribolos.yaml`
   ([AGENTS.md](AGENTS.md) tells it how).
2. [chai-bot-membership.yml](.github/workflows/chai-bot-membership.yml) merges
   the PR if it is from chai-bot and makes only that change. Otherwise the PR
   stays open with a comment saying why.
3. [peribolos.yml](.github/workflows/peribolos.yml) applies `peribolos.yaml`
   on every change to `main`, which sends the invitation.

Peribolos removes members and pending invitations not in `peribolos.yaml`, so
make all membership changes there rather than in the GitHub UI.

## Setup

Both workflows need a GitHub App installed on this org, with these permissions:

| Scope        | Permission    | Access       |
| ------------ | ------------- | ------------ |
| Organization | Members       | Read & write |
| Repository   | Contents      | Read & write |
| Repository   | Pull requests | Read & write |

Then, in this repo's Actions settings, set the App's client ID as the
`GOVERNANCE_CLIENT_ID` variable and its private key as the
`GOVERNANCE_PRIVATE_KEY` secret.

## Tests

```bash
python3 scripts/test_chai_bot_membership.py
```
