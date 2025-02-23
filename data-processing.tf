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

# Hudi step functions pipeline
resource "aws_iam_role" "sfn_role" {
  name = "lakehouse-sfn-pipeline-iam-rol"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Sid    = ""
        Principal = {
          Service = "states.amazonaws.com"
        }
      },
    ]
  })
  managed_policy_arns = ["arn:aws:iam::aws:policy/AdministratorAccess"]
}
data "template_file" "state_machine_definition_hudi" {
  template = file("./state-machines/pipeline.json")
  vars = {
    replication_task_arn = module.database_migration_service.replication_tasks["cdc_ex"].replication_task_arn
    fl_job_name          = aws_glue_job.hudi_full_load_job.name
    cdc_job_name         = aws_glue_job.hudi_cdc_job.name
    gold_job_name        = aws_glue_job.hudi_gold_elt_job.name
    sns_monitoring       = aws_sns_topic.monitoring_notifications.arn
  }
}
resource "aws_sfn_state_machine" "hudi_fl_cdc_pipeline" {
  name     = "hudi-fl-cdc-pipeline"
  role_arn = aws_iam_role.sfn_role.arn

  definition = data.template_file.state_machine_definition_hudi.rendered
}

# Event Bridge Schedule for Hudi pipeline
resource "aws_iam_role" "bridge_role" {
  name = "eventbridge-scheduler-iam-rol"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Sid    = ""
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
      },
    ]
  })
  managed_policy_arns = ["arn:aws:iam::aws:policy/AdministratorAccess"]
}
resource "aws_scheduler_schedule" "hudi_fl_cdc_pipeline" {
  name       = "hudi-fl-cdc-pipeline"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }
  state               = "DISABLED"
  schedule_expression = "cron(0 * ? * * *)" # every hour
  #   schedule_expression_timezone = "America/Bogota"


  target {
    arn      = aws_sfn_state_machine.hudi_fl_cdc_pipeline.arn
    role_arn = aws_iam_role.bridge_role.arn

    input = jsonencode({
      Commet = "Start Pipeline"
    })
  }
}

# Hudi FL and CDC glue jobs
resource "aws_glue_job" "hudi_full_load_job" {
  name              = "hudi-full-load-job"
  role_arn          = aws_iam_role.glue_role.arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = "2"
  max_retries       = 0
  timeout           = 15
  execution_class   = "FLEX"

  command {
    script_location = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/hudi/glueScripts/full_load.py"
  }

  default_arguments = {
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--enable-glue-datacatalog"          = "true"
    "--enable-job-insights"              = "true"
    "--datalake-formats"                 = "hudi"
    "--conf"                             = "spark.serializer=org.apache.spark.serializer.KryoSerializer --conf spark.sql.hive.convertMetastoreParquet=false"
    "--TempDir"                          = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/sparkHistoryLogs/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/hudi/libraries/hudi_common_library.py"
    "--job-bookmark-option"              = "job-bookmark-disable"
  }
}
resource "aws_glue_job" "hudi_cdc_job" {
  name              = "hudi-cdc-job"
  role_arn          = aws_iam_role.glue_role.arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = "2"
  max_retries       = 0
  timeout           = 15
  execution_class   = "FLEX"

  command {
    script_location = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/hudi/glueScripts/cdc.py"
  }
  default_arguments = {
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--enable-glue-datacatalog"          = "true"
    "--enable-job-insights"              = "true"
    "--datalake-formats"                 = "hudi"
    "--conf"                             = "spark.serializer=org.apache.spark.serializer.KryoSerializer --conf spark.sql.hive.convertMetastoreParquet=false"
    "--TempDir"                          = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/sparkHistoryLogs/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/hudi/libraries/hudi_common_library.py"
    "--job-bookmark-option"              = "job-bookmark-enable"
  }
}
resource "aws_glue_job" "hudi_gold_elt_job" {
  name              = "hudi-gold-etl-job"
  role_arn          = aws_iam_role.glue_role.arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = "2"
  max_retries       = 0
  timeout           = 15
  execution_class   = "FLEX"

  command {
    script_location = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/hudi/glueScripts/gold_etl_job.py"
  }
  default_arguments = {
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--enable-glue-datacatalog"          = "true"
    "--enable-job-insights"              = "true"
    "--datalake-formats"                 = "hudi"
    "--conf"                             = "spark.serializer=org.apache.spark.serializer.KryoSerializer --conf spark.sql.hive.convertMetastoreParquet=false"
    "--TempDir"                          = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/sparkHistoryLogs/"
    "--extra-py-files"                   = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/hudi/libraries/hudi_common_library.py"
    "--job-bookmark-option"              = "job-bookmark-disable"
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
#     script_location = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/iceberg/glueScripts/gold_etl_job.py"
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
#     script_location = "s3://${aws_s3_bucket.dependencies.id}/glueAssets/delta/glueScripts/gold_etl_job.py"
#   }
# }