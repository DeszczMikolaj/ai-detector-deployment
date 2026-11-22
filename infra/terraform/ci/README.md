# Stack `ci`: dostęp GitHub Actions do AWS (ADR-0017)

Dostawca OIDC GitHuba i dwie role IAM:

| Rola | Kto może jej użyć (warunek `sub` w tokenie) | Uprawnienia |
|---|---|---|
| `github-actions-ai-text-detector-plan` | workflow uruchomiony przez PR z tego repo (`repo:…:pull_request`). PR-y z forków nie dostają tokenu OIDC. | `ReadOnlyAccess` + zapis i usuwanie pliku blokady stanu (`envs/*.tflock`) |
| `github-actions-ai-text-detector-deploy` | tylko job w GitHub Environment `dev` (`repo:…:environment:dev`) | `PowerUserAccess` + IAM wyłącznie na rolach `ai-text-detector-*` + jawny zakaz zmiany ról CI i dostawcy OIDC |

**Ten stack stosuje wyłącznie człowiek, nigdy CI.** Inaczej workflow mógłby sam sobie dopisać uprawnienia. Z tego samego powodu nazwy ról CI nie zaczynają się od `ai-text-detector-`.

## Wdrożenie (PowerShell, jednorazowo)
```powershell
cd infra\terraform\ci
terraform init
terraform plan -out ci.tfplan      # oczekiwane: 7 to add, 0 to change, 0 to destroy
terraform apply ci.tfplan
terraform output
```

## Konfiguracja po stronie GitHuba
1. **Settings → Environments → New environment → `dev`:**
   - *Deployment branches and tags* → **Selected branches** → `main`,
   - *Required reviewers* → co najmniej jedna osoba (wdrożenie czeka na zatwierdzenie),
   - *Environment variables* → `AWS_DEPLOY_ROLE_ARN` = output `deploy_role_arn`.
2. **Settings → Secrets and variables → Actions → Variables → New repository variable:**
   `AWS_PLAN_ROLE_ARN` = output `plan_role_arn`.

ARN-y ról nie są sekretami. O tym, kto może przyjąć rolę, decyduje polityka zaufania w AWS, a nie znajomość ARN-u. Dlatego trzymamy je jako *variables*, a nie *secrets*.

## Użycie w workflowie
```yaml
permissions:
  id-token: write   # pozwala jobowi poprosić GitHub o token OIDC
  contents: read
steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: ${{ vars.AWS_PLAN_ROLE_ARN }}
      aws-region: eu-north-1
```
