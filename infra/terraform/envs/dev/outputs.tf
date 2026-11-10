output "inference_repository_url" {
  description = "Adres repozytorium ECR — cel dla `docker push`."
  value       = aws_ecr_repository.inference.repository_url
}

output "inference_function_name" {
  value = local.inference_enabled ? aws_lambda_function.inference[0].function_name : null
}

output "inference_version" {
  description = "Wersja Lambdy, na którą wskazuje alias champion."
  value       = local.inference_enabled ? aws_lambda_alias.champion[0].function_version : null
}

output "evaluate_url" {
  description = "Publiczny endpoint oceny tekstu."
  value       = local.inference_enabled ? "${aws_apigatewayv2_stage.default[0].invoke_url}evaluate" : null
}

output "artifacts_bucket_name" {
  description = "Bucket na modele, zbiory danych i wagi LLM."
  value       = aws_s3_bucket.artifacts.bucket
}
