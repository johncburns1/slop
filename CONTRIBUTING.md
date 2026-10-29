# Contributing

These rules apply to humans and AI agents alike.

## Pull requests

- Each PR makes one behavioral change.
- Target `main`. Don't stack PRs on other branches; rebase onto `main` if it moves.
- If Verify needs more than about 3 bullets, split the PR.
- Fill in the template in [.github/pull_request_template.md](.github/pull_request_template.md). CI checks must pass (see [README.md](README.md#development)).
- In Verify, link the CI run whose job summary shows the validation report (`.validation/report.md`).

## Priority labels

Every workstream gets one of `High`, `Medium`, or `Low`.

## Workstream states

drafting → needs review → addressing feedback → ready to merge → verified

- **drafting**: work in progress, usually a draft PR.
- **needs review**: waiting on a human.
- **addressing feedback**: the author is responding to review.
- **ready to merge**: approved and CI is green.
- **verified**: merged and confirmed working on `main`.
