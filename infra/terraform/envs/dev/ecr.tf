# Repozytorium obrazów dla Lambdy inference (ADR-0004, ADR-0012).

resource "aws_ecr_repository" "inference" {
  name = "${var.project}/inference"

  # Tag = konkretna wersja kodu; nadpisanie tagu innym obrazem jest zablokowane.
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "inference" {
  repository = aws_ecr_repository.inference.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Usuwaj nieotagowane warstwy po 1 dniu"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Trzymaj 10 ostatnich obrazów"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      },
    ]
  })
}

# Pozwala usłudze Lambda (tylko funkcjom z tego konta i regionu) pobierać obrazy z repozytorium.
data "aws_iam_policy_document" "inference_ecr" {
  statement {
    sid    = "LambdaPull"
    effect = "Allow"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "aws:sourceArn"
      values   = ["arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:*"]
    }
  }
}

resource "aws_ecr_repository_policy" "inference" {
  repository = aws_ecr_repository.inference.name
  policy     = data.aws_iam_policy_document.inference_ecr.json
}
