# Bucket na artefakty ML: modele (ADR-0012), zbiory danych, lustro wag LLM (ADR-0014), backupy (ADR-0005).
#
# Układ prefiksów (konwencja, nie wymuszana przez S3):
#   models/<wersja>/      model.ubj, feature_profile.json, metadata.json, checksums.json — niezmienne po wysłaniu
#   datasets/<nazwa>/<wersja>/  data.tsv, labels.tsv, manifest.json — niezmienne po wysłaniu
#   llm/<rodzina>/<wersja>/     wagi lokalnych LLM (ADR-0014)
#   backups/                    pg_dump bazy (ADR-0005)

locals {
  artifacts_bucket_name = "${var.project}-artifacts-${data.aws_caller_identity.current.account_id}-${var.region}"
}

resource "aws_s3_bucket" "artifacts" {
  bucket = local.artifacts_bucket_name

  # Modele i dane treningowe — usunięcie bucketa wymaga świadomej zmiany kodu.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Wersjonowanie: przypadkowe nadpisanie lub usunięcie modelu/zbioru da się cofnąć.
resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    # Poprzednie wersje nadpisanych/usuniętych obiektów — okno na odzyskanie.
    noncurrent_version_expiration {
      noncurrent_days = var.artifacts_noncurrent_retention_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  depends_on = [aws_s3_bucket_versioning.artifacts]
}

data "aws_iam_policy_document" "artifacts" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.artifacts.arn,
      "${aws_s3_bucket.artifacts.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  policy = data.aws_iam_policy_document.artifacts.json

  depends_on = [aws_s3_bucket_public_access_block.artifacts]
}
