resource "aws_iam_role" "glue_role" {
  name = "accesoglue-iam-rol"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Sid    = ""
        Principal = {
          Service = "glue.amazonaws.com"
        }
      },
    ]
  })
  managed_policy_arns = ["arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole", "arn:aws:iam::aws:policy/AmazonS3FullAccess", "arn:aws:iam::aws:policy/SecretsManagerReadWrite"]
}

# Hudi FL and CDC glue jobs
resource "aws_glue_job" "hudi_full_load_job" {
  name     = "hudi-full-load-job"
  role_arn = aws_iam_role.glue_role.arn

  command {
    script_location = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/hudi/glueScripts/full_load.py"
  }
}
resource "aws_glue_job" "hudi_cdc_job" {
  name     = "hudi-cdc-job"
  role_arn = aws_iam_role.glue_role.arn

  command {
    script_location = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/hudi/glueScripts/cdc.py"
  }
}
resource "aws_glue_job" "hudi_gold_elt_job" {
  name     = "hudi-gold-etl-job"
  role_arn = aws_iam_role.glue_role.arn

  command {
    script_location = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/hudi/glueScripts/gold_elt_job.py"
  }
}
# # Iceberg FL and CDC glue jobs
# resource "aws_glue_job" "full_load_iceberg_job" {
#   name     = "full-load-iceberg-job"
#   role_arn = aws_iam_role.glue_role.arn

#   command {
#     script_location = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/iceberg/glueScripts/full_load.py"
#   }
# }
# resource "aws_glue_job" "cdc_iceberg_job" {
#   name     = "cdc-iceberg-job"
#   role_arn = aws_iam_role.glue_role.arn

#   command {
#     script_location = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/iceberg/glueScripts/cdc.py"
#   }
# }
# resource "aws_glue_job" "iceberg_gold_elt_job" {
#   name     = "iceberg-gold-etl-job"
#   role_arn = aws_iam_role.glue_role.arn

#   command {
#     script_location = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/iceberg/glueScripts/gold_elt_job.py"
#   }
# }
# # Delta FL and CDC glue jobs
# resource "aws_glue_job" "full_load_delta_job" {
#   name     = "full-load-delta-job"
#   role_arn = aws_iam_role.glue_role.arn

#   command {
#     script_location = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/delta/glueScripts/full_load.py"
#   }
# }
# resource "aws_glue_job" "cdc_delta_job" {
#   name     = "cdc-delta-job"
#   role_arn = aws_iam_role.glue_role.arn

#   command {
#     script_location = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/delta/glueScripts/cdc.py"
#   }
# }
# resource "aws_glue_job" "delta_gold_elt_job" {
#   name     = "delta-gold-etl-job"
#   role_arn = aws_iam_role.glue_role.arn

#   command {
#     script_location = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/delta/glueScripts/gold_elt_job.py"
#   }
# }