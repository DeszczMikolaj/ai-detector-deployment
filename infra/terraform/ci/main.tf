# Dostęp GitHub Actions do AWS bez stałych kluczy (ADR-0017).
#
# GitHub wystawia przy każdym uruchomieniu workflowu krótkotrwały token OIDC. AWS STS wymienia go
# na tymczasowe poświadczenia roli — o ile token spełnia warunki z polityki zaufania roli
# (repozytorium, typ zdarzenia, environment). Nie ma klucza, który mógłby wyciec.
#
# Nazwy ról CI celowo NIE zaczynają się od var.project: rola wdrożeniowa zarządza rolami
# "${var.project}-*" (np. rola Lambdy), więc nie może dzięki temu zmienić samej siebie.

locals {
  account_id       = data.aws_caller_identity.current.account_id
  oidc_host        = "token.actions.githubusercontent.com"
  state_bucket     = "${var.project}-tfstate-${local.account_id}-${var.region}"
  plan_role_name   = "github-actions-${var.project}-plan"
  deploy_role_name = "github-actions-${var.project}-deploy"
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://${local.oidc_host}"
  client_id_list = ["sts.amazonaws.com"]
  # thumbprint_list pominięte: dla GitHub OIDC AWS weryfikuje certyfikat samodzielnie.
}

# ---------- rola plan: każdy PR z tego repozytorium ----------
# PR-y z forków nie dostają tokenu OIDC (GitHub nie nadaje im id-token: write), więc publiczne repo
# nie otwiera tej roli dla obcych. Uprawnienia: odczyt konta + stan Terraformu (z blokadą).

data "aws_iam_policy_document" "plan_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = ["repo:${var.github_repository}:pull_request"]
    }
  }
}

# Opisy ról w IAM: tylko ASCII/Latin-1 — API odrzuca polskie litery i półpauzę.
resource "aws_iam_role" "plan" {
  name                 = local.plan_role_name
  description          = "GitHub Actions: terraform plan on PRs, read-only (ADR-0017)"
  assume_role_policy   = data.aws_iam_policy_document.plan_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_readonly" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# terraform plan z use_lockfile zapisuje i usuwa plik blokady obok stanu.
data "aws_iam_policy_document" "plan_state_lock" {
  statement {
    sid       = "StateLockFiles"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${local.state_bucket}/envs/*.tflock"]
  }
}

resource "aws_iam_role_policy" "plan_state_lock" {
  name   = "terraform-state-lock"
  role   = aws_iam_role.plan.id
  policy = data.aws_iam_policy_document.plan_state_lock.json
}

# ---------- rola deploy: tylko job w GitHub Environment z zatwierdzeniem ----------
# Gdy job używa `environment: dev`, token ma sub = repo:<repo>:environment:dev. Environment
# w GitHubie jest ograniczony do gałęzi main i wymaga zatwierdzenia przez wskazaną osobę.

data "aws_iam_policy_document" "deploy_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = ["repo:${var.github_repository}:environment:${var.github_deploy_environment}"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = local.deploy_role_name
  description          = "GitHub Actions: build, terraform apply envs/*, Lambda alias switch (ADR-0017)"
  assume_role_policy   = data.aws_iam_policy_document.deploy_trust.json
  max_session_duration = 3600
}

# Wszystko poza IAM i Organizations (ECR, Lambda, API Gateway, S3, CloudWatch, ...).
resource "aws_iam_role_policy_attachment" "deploy_poweruser" {
  role       = aws_iam_role.deploy.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

data "aws_iam_policy_document" "deploy_iam" {
  # Terraform w envs/* tworzy role usług (np. rolę wykonawczą Lambdy) — tylko z prefiksem projektu.
  statement {
    sid = "ManageProjectRoles"

    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:UpdateRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:PutRolePolicy",
      "iam:GetRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:ListRolePolicies",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:ListRoleTags",
    ]
    resources = ["arn:aws:iam::${local.account_id}:role/${var.project}-*"]
  }

  # Przekazanie roli usłudze (np. Lambda przyjmuje swoją rolę) — tylko role projektu i tylko usługom.
  statement {
    sid       = "PassProjectRolesToServices"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/${var.project}-*"]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com", "batch.amazonaws.com", "ecs-tasks.amazonaws.com", "ec2.amazonaws.com"]
    }
  }

  # Bezpiecznik: CI nigdy nie zmienia ról CI ani zaufania do GitHuba, nawet gdyby prefiks się zgadzał.
  statement {
    sid    = "DenyChangingCiAccess"
    effect = "Deny"

    actions = [
      "iam:Attach*",
      "iam:Create*",
      "iam:Delete*",
      "iam:Detach*",
      "iam:Put*",
      "iam:Update*",
      "iam:Tag*",
      "iam:Untag*",
      "iam:AddClientIDToOpenIDConnectProvider",
      "iam:RemoveClientIDFromOpenIDConnectProvider",
    ]
    resources = [
      aws_iam_role.plan.arn,
      "arn:aws:iam::${local.account_id}:role/${local.deploy_role_name}",
      aws_iam_openid_connect_provider.github.arn,
    ]
  }
}

resource "aws_iam_role_policy" "deploy_iam" {
  name   = "project-roles-only"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy_iam.json
}
