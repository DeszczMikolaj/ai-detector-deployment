output "state_bucket_name" {
  description = "Nazwa bucketa na stan Terraform — wpisz ją w bloki backend \"s3\" pozostałych katalogów."
  value       = aws_s3_bucket.tfstate.bucket
}

output "account_id" {
  description = "ID konta, na którym utworzono bucket (kontrola, czy to właściwe konto)."
  value       = data.aws_caller_identity.current.account_id
}

output "region" {
  value = var.region
}
