## Summary

<!-- What changed, and why does it matter to users or operators? -->

## Change type

- [ ] Feature
- [ ] Bug fix
- [ ] Documentation
- [ ] Refactor or maintenance
- [ ] Security or privacy
- [ ] Breaking change (explain below)

## Verification

<!-- List the commands you ran and the result. Include screenshots for meaningful UI changes. -->

- [ ] Backend tests (pytest)
- [ ] Frontend tests (npm test -- --watch=false)
- [ ] Frontend production build (npm run build)
- [ ] Compose validation (docker compose config --quiet)
- [ ] Browser or mobile smoke test (when UI changed)

## Safety and compatibility

- [ ] No secrets, customer data, or runtime databases are included.
- [ ] Synthetic data is visibly labeled and is not presented as connected data.
- [ ] Dataset changes include provenance, license, label source, split/eligibility,
      regenerated hashes, and no private operational data.
- [ ] Evidence, counter-evidence, uncertainty, and feedback behavior remains explainable.
- [ ] API and database compatibility is preserved, or a migration and rollback plan is included.
- [ ] This change does not add autonomous deployment, rollback, shell execution, cluster credentials, or remediation.

## Documentation and rollout

<!-- Note docs, migrations, config changes, feature flags, rollout, and rollback steps. -->

## Reviewer notes

<!-- Call out risky areas, open questions, or follow-up work. -->
