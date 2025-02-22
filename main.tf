
data "aws_availability_zones" "available" {}
data "aws_caller_identity" "current" {}
locals {
  vpc_cidr = "10.0.0.0/16"
  azs      = slice(data.aws_availability_zones.available.names, 0, 3)
}

# this lambda is used to create sample data in the RDS database and setup necessary binary logging retention
module "lambda_function_in_vpc" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "7.20.1"

  function_name = "lambda-table-create"
  description   = "My awesome lambda function"
  handler       = "index.lambda_handler"
  runtime       = "python3.12"

  source_path = "./lambda-code"

  attach_policy_json = true
  policy_json        = <<-EOT
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["*"],
                "Resource": ["*"]
            }
        ]
    }
  EOT

  environment_variables = {
    USERNAME = module.db.db_instance_username
    PASSWORD = "Password1234."
    RDS_HOST = module.db.db_instance_address
    RDS_PORT = module.db.db_instance_port
    RDS_DATABASE = module.db.db_instance_name
  }
  vpc_subnet_ids                     = module.vpc.database_subnets
  vpc_security_group_ids             = [module.security_group.security_group_id]
}
