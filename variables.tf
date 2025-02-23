# AWS Region
variable "aws_region" {
  type        = string
  nullable    = false
  description = "the aws region for the deployment"
  default     = "us-east-1"
}
# AWS Profile
variable "profile" {
  type        = string
  nullable    = false
  description = "name of the profile stored in ~/.aws/credentials"
  sensitive   = true
  default     = "default"
}
# Environment to deploy [dev , qa, demo, prod]
variable "env_name" {
  description = "The name of the workspace to use for this deployment."
  default     = "dev"
}
# variable "administrato_user_arn" {
#   description = "arn del usuario administrador"
#   type        = string
# }
# AWS Region
variable "monitoring_emails" {
  type        = set(string)
  nullable    = false
  description = "emails for pipelines monitoring"
  default     = []
}