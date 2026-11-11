# Lambda inference + API Gateway (ADR-0004). Tworzone dopiero, gdy podano var.inference_image_tag.

locals {
  inference_enabled   = var.inference_image_tag != null
  inference_name      = "${var.project}-inference"
  inference_model_uri = "s3://${aws_s3_bucket.artifacts.bucket}/models/${var.inference_model_version}/"
}

# --- Rola wykonawcza Lambdy: zapis własnych logów + odczyt modeli z S3 ---

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "inference" {
  count              = local.inference_enabled ? 1 : 0
  name               = "${local.inference_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

data "aws_iam_policy_document" "inference_logs" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.inference_name}:*"]
  }
}

resource "aws_iam_role_policy" "inference_logs" {
  count  = local.inference_enabled ? 1 : 0
  name   = "logs"
  role   = aws_iam_role.inference[0].id
  policy = data.aws_iam_policy_document.inference_logs.json
}

# Odczyt artefaktów modeli (ADR-0012): tylko GetObject, tylko prefiks models/.
# Bez ListBucket — handler pobiera znane nazwy plików; brak pliku daje 403 zamiast 404.
data "aws_iam_policy_document" "inference_models" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/models/*"]
  }
}

resource "aws_iam_role_policy" "inference_models" {
  count  = local.inference_enabled ? 1 : 0
  name   = "read-models"
  role   = aws_iam_role.inference[0].id
  policy = data.aws_iam_policy_document.inference_models.json
}

# Grupa logów tworzona jawnie, żeby ustawić retencję (domyślnie logi żyją wiecznie i kosztują).
resource "aws_cloudwatch_log_group" "inference" {
  count             = local.inference_enabled ? 1 : 0
  name              = "/aws/lambda/${local.inference_name}"
  retention_in_days = var.log_retention_days
}

# --- Funkcja ---

resource "aws_lambda_function" "inference" {
  count         = local.inference_enabled ? 1 : 0
  function_name = local.inference_name
  role          = aws_iam_role.inference[0].arn

  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.inference.repository_url}:${var.inference_image_tag}"
  architectures = ["x86_64"] # ts2vg ma skompilowane rozszerzenia (ADR-0005)

  memory_size = var.inference_memory_mb
  timeout     = var.inference_timeout_s
  publish     = true # każda zmiana = nowa, niezmienna wersja (ADR-0012)

  environment {
    variables = {
      MAX_TEXT_CHARS = tostring(var.inference_max_text_chars)
      MODEL_URI      = local.inference_model_uri
      SHAP_METHOD    = var.inference_shap_method
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.inference,
    aws_iam_role_policy.inference_logs,
    aws_iam_role_policy.inference_models,
    aws_ecr_repository_policy.inference,
  ]
}

# Alias `champion` — API zawsze woła alias, nigdy wersję bezpośrednio (ADR-0004, ADR-0012).
# TODO: na etapie tracera Terraform przestawia alias na najnowszą wersję przy każdym apply.
# Docelowo (ADR-0012) alias przestawia admin-api przy promocji — wtedy dodać:
#   lifecycle { ignore_changes = [function_version] }
resource "aws_lambda_alias" "champion" {
  count            = local.inference_enabled ? 1 : 0
  name             = "champion"
  function_name    = aws_lambda_function.inference[0].function_name
  function_version = aws_lambda_function.inference[0].version
}

# --- API Gateway (HTTP API) ---

resource "aws_apigatewayv2_api" "public" {
  count         = local.inference_enabled ? 1 : 0
  name          = "${var.project}-public-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_methods = ["POST", "OPTIONS"]
    allow_headers = ["content-type"]
    allow_origins = ["*"] # TODO: zawęzić do domeny frontendu, gdy powstanie
    max_age       = 3600
  }
}

resource "aws_apigatewayv2_integration" "inference" {
  count                  = local.inference_enabled ? 1 : 0
  api_id                 = aws_apigatewayv2_api.public[0].id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_alias.champion[0].invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 29000
}

resource "aws_apigatewayv2_route" "evaluate" {
  count     = local.inference_enabled ? 1 : 0
  api_id    = aws_apigatewayv2_api.public[0].id
  route_key = "POST /evaluate"
  target    = "integrations/${aws_apigatewayv2_integration.inference[0].id}"
}

resource "aws_apigatewayv2_stage" "default" {
  count       = local.inference_enabled ? 1 : 0
  api_id      = aws_apigatewayv2_api.public[0].id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = var.api_throttle_rate
    throttling_burst_limit = var.api_throttle_burst
  }
}

resource "aws_lambda_permission" "apigw" {
  count         = local.inference_enabled ? 1 : 0
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.inference[0].function_name
  qualifier     = aws_lambda_alias.champion[0].name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.public[0].execution_arn}/*/*/evaluate"
}
