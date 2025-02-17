# AWS Region
variable "aws_region" {
  type        = string
  nullable    = false
  description = "the aws region for the deployment"
}
# AWS Profile
variable "profile" {
  type        = string
  nullable    = false
  description = "name of the profile stored in ~/.aws/credentials"
  sensitive   = true
}
# Environment to deploy [dev , qa, demo, prod]
variable "env_name" {
  description = "The name of the workspace to use for this deployment."
}
variable "backend_bucket" {
  type = string
  description = "the bucket for the backend aws configuration"
}
