# AWS Batch dla ścieżki administracyjnej: generacja próbek AI lokalnymi LLM-ami, trening, ewaluacja
# (ADR-0003, ADR-0010). Nie dotyczy oceny tekstu przez klienta — to Lambda (ADR-0004).
#
# Dwa compute environmenty EC2 i dwie kolejki, bez automatycznego fallbacku między nimi (ADR-0010, pkt 3):
#   spot      — domyślna, tania; zadania podzielne na porcje i idempotentne,
#   ondemand  — tryb awaryjny (przełącznik w panelu admina).
# min_vcpus = 0: bez zadań nie działa żadna instancja i nic nie kosztuje.
#
# Definicje zadań (obraz workera, vCPU/pamięć, rola zadania z dostępem do S3) — osobny PR,
# razem z kodem workera i ustaleniami z docs/design/retraining-pipeline-brief.md.

# ---------- sieć: domyślny VPC (świadomy skrót) ----------
# Publiczne podsieci z publicznym IP, bez ruchu przychodzącego — pozwala uniknąć NAT Gateway (~$35/mies.,
# ADR-0008). Produkcyjnie: własny VPC, prywatne podsieci, VPC endpoints do ECR, S3 i CloudWatch Logs.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

resource "aws_security_group" "batch_workers" {
  name        = "${var.project}-batch-workers"
  description = "AWS Batch workers: egress only (ECR, S3, CloudWatch Logs), no inbound"
  vpc_id      = data.aws_vpc.default.id
}

# Brak reguł ingress = brak ruchu przychodzącego (także SSH).
resource "aws_vpc_security_group_egress_rule" "batch_workers_https" {
  security_group_id = aws_security_group.batch_workers.id
  description       = "HTTPS to AWS APIs and model downloads"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

# DNS (resolver VPC) i czas (Amazon Time Sync) to adresy link-local — security group ich nie filtruje.
# HTTP (80) celowo nie jest otwarte: ECR, S3, repozytoria AL2023 i pobieranie modeli działają po HTTPS.

# ---------- rola instancji (ECS agent na hoście) ----------
# Pobieranie obrazów z ECR, rejestracja w klastrze ECS, logi. Dostęp zadań do S3 da osobna rola zadania.

data "aws_iam_policy_document" "batch_instance_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "batch_instance" {
  name               = "${var.project}-batch-instance-role"
  assume_role_policy = data.aws_iam_policy_document.batch_instance_trust.json
}

resource "aws_iam_role_policy_attachment" "batch_instance_ecs" {
  role       = aws_iam_role.batch_instance.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_instance_profile" "batch_instance" {
  name = "${var.project}-batch-instance-profile"
  role = aws_iam_role.batch_instance.name
}

# ---------- compute environments ----------
# Bez service_role: Batch używa roli powiązanej z usługą (AWSServiceRoleForBatch), tworzonej automatycznie.
# Spot z SPOT_CAPACITY_OPTIMIZED nie wymaga roli Spot Fleet.

locals {
  batch_compute = {
    spot = {
      type                = "SPOT"
      allocation_strategy = "SPOT_CAPACITY_OPTIMIZED"
    }
    ondemand = {
      type                = "EC2"
      allocation_strategy = "BEST_FIT_PROGRESSIVE"
    }
  }
}

resource "aws_batch_compute_environment" "workers" {
  for_each = local.batch_compute

  name = "${var.project}-${each.key}"
  type = "MANAGED"

  compute_resources {
    type                = each.value.type
    allocation_strategy = each.value.allocation_strategy
    min_vcpus           = 0
    max_vcpus           = var.batch_max_vcpus
    instance_type       = var.batch_instance_types
    instance_role       = aws_iam_instance_profile.batch_instance.arn
    subnets             = data.aws_subnets.default.ids
    security_group_ids  = [aws_security_group.batch_workers.id]

    ec2_configuration {
      image_type = "ECS_AL2023"
    }

    tags = {
      Name        = "${var.project}-batch-${each.key}"
      Project     = var.project
      Environment = "dev"
    }
  }

  # Większość zmian compute_resources (np. max_vcpus, typy instancji) AWS stosuje w miejscu. Zmiana wymagająca
  # odtworzenia (np. nazwa) wymaga najpierw odłączenia środowiska od kolejki — robić ręcznie, nie przez CI.

  depends_on = [aws_iam_role_policy_attachment.batch_instance_ecs]
}

# ---------- kolejki ----------
# Zadanie wiszące w RUNNABLE na czele kolejki dłużej niż batch_runnable_timeout_s z powodu braku pojemności
# lub błędnej konfiguracji jest anulowane (ADR-0010, pkt 5). Czekanie na wolne vCPU w ramach max_vcpus
# (dużo porcji naraz) nie jest blokadą i nie podlega tej akcji.

locals {
  batch_runnable_block_reasons = [
    "CAPACITY:INSUFFICIENT_INSTANCE_CAPACITY",
    "MISCONFIGURATION:COMPUTE_ENVIRONMENT_MAX_RESOURCE",
    "MISCONFIGURATION:JOB_RESOURCE_REQUIREMENT",
    "MISCONFIGURATION:SERVICE_ROLE_PERMISSIONS",
  ]
}

resource "aws_batch_job_queue" "workers" {
  for_each = local.batch_compute

  name     = "${var.project}-${each.key}"
  state    = "ENABLED"
  priority = 1

  compute_environment_order {
    order               = 1
    compute_environment = aws_batch_compute_environment.workers[each.key].arn
  }

  dynamic "job_state_time_limit_action" {
    for_each = local.batch_runnable_block_reasons

    content {
      action           = "CANCEL"
      state            = "RUNNABLE"
      max_time_seconds = var.batch_runnable_timeout_s
      reason           = job_state_time_limit_action.value
    }
  }
}
