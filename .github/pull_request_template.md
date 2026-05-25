## Summary

- [ ] Briefly describe the change.
- [ ] Note any user-facing behavior or workflow changes.

## Test Plan

- [ ] `python -W error -m pytest -q`
- [ ] `python build/package.py`

## Policy Checklist

- [ ] `CHANGELOG.md` `[Unreleased]` has matching entries, or this PR is docs-only / test-only / chore-only.
- [ ] `VERSION` is consistent with the intended release state.
- [ ] This PR body checklist is fully checked.
- [ ] `python -m policy_check --repo .` reports no failures.
- [ ] Any repo-specific test, lint, and build commands required by this change have passed.
- [ ] Any skipped checks use only allowed policy exemption labels and include a reason.

## Exemptions / Notes

- None.
