terraform {
  backend "s3" {
    encrypt = true
    bucket = var.backend_bucket
    key    = "project-name/terraform.tfstate"
    region = var.aws_region
  }
}
