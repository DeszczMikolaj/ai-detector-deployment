output "plan_role_arn" {
  description = "Wpisz jako zmienną repozytorium AWS_PLAN_ROLE_ARN (Settings → Secrets and variables → Actions → Variables)."
  value       = aws_iam_role.plan.arn
}

output "deploy_role_arn" {
  description = "Wpisz jako zmienną środowiska dev: AWS_DEPLOY_ROLE_ARN (Settings → Environments → dev → Variables)."
  value       = aws_iam_role.deploy.arn
}
