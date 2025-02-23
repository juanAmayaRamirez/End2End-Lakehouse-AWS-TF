module "db" {
  source = "terraform-aws-modules/rds/aws"

  identifier = "sample-mysql-db"

  # All available versions: http://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_MySQL.html#MySQL.Concepts.VersionMgmt
  engine               = "mysql"
  engine_version       = "8.0"
  family               = "mysql8.0" # DB parameter group
  major_engine_version = "8.0"      # DB option group
  instance_class       = "db.t3.micro"

  allocated_storage     = 20
    #   max_allocated_storage = 100
  
  manage_master_user_password = false
  db_name  = "completeMysql"
  username = "complete_mysql"
  password = "Password1234."
  port     = 3306

  multi_az               = false
  db_subnet_group_name   = module.vpc.database_subnet_group
  vpc_security_group_ids = [module.security_group.security_group_id]

  maintenance_window              = "Mon:00:00-Mon:03:00"
  backup_window                   = "03:00-06:00"
  backup_retention_period         = 7
  apply_immediately               = true
  delete_automated_backups        = true
    #   enabled_cloudwatch_logs_exports = ["general"]
    #   create_cloudwatch_log_group     = false

    #   skip_final_snapshot = false
    #   deletion_protection = false

    #   performance_insights_enabled          = false
    #   performance_insights_retention_period = 7
    #   create_monitoring_role                = false
    #   monitoring_interval                   = 60

  parameters = [
    {
      name  = "character_set_client"
      value = "utf8mb4"
    },
    {
      name  = "character_set_server"
      value = "utf8mb4"
    },
    {
        name  = "binlog_format"
        value = "ROW"
    },
    {
        name  = "binlog_row_image"
        value = "Full"
    },
    {
        name  = "log_bin_trust_function_creators"
        value = "1"
    }
  ]

}

module "database_migration_service" {
  source  = "terraform-aws-modules/dms/aws"
  version = "= 2.4"

  # Subnet group
  repl_subnet_group_name        = "lakehouse-dms-subnet-group"
  repl_subnet_group_description = "DMS Subnet group"
  repl_subnet_group_subnet_ids  = module.vpc.private_subnets

  # Instance
    #   repl_instance_allocated_storage            = 64
    #   repl_instance_auto_minor_version_upgrade   = true
    #   repl_instance_allow_major_version_upgrade  = true
  repl_instance_apply_immediately            = true
    #   repl_instance_engine_version               = "3.5.2"
  repl_instance_multi_az                     = false
  repl_instance_preferred_maintenance_window = "sun:10:30-sun:14:30"
  repl_instance_publicly_accessible          = true
  repl_instance_class                        = "dms.t3.micro"
  repl_instance_id                           = "lakehouse-dms-instance"
  repl_instance_vpc_security_group_ids       = [module.security_group.security_group_id]

  endpoints = {
    source = {
      endpoint_id                 = "source-mysql-rds"
      endpoint_type               = "source"
      database_name               = module.db.db_instance_name
      server_name                 = module.db.db_instance_address
      engine_name                 = module.db.db_instance_engine
      port                        = module.db.db_instance_port
      username                    = module.db.db_instance_username
      password                    = "Password1234."
      tags                        = { EndpointType = "source" }
    }
  }
  s3_endpoints = {
    destination = {
        endpoint_id              = "target-s3-bronce"
        endpoint_type            = "target"
        bucket_name              = aws_s3_bucket.bronce.id
        bucket_folder            = "rds"
        data_format              = "parquet"
        date_partition_enabled   = false
        compression_type         = "NONE"
        service_access_role_arn  = aws_iam_role.dms_role.arn
        timestamp_column_name    = "ts"
        include_op_for_full_load = true
        cdc_min_file_size        = 32000
        cdc_max_batch_interval   = 30
    }
  }
  replication_tasks = {
    cdc_ex = {
      replication_task_id       = "lakehouse-dms-task"
      migration_type            = "full-load-and-cdc"
      replication_task_settings = file("dms_configs/task_settings.json")
      table_mappings            = file("dms_configs/table_mappings.json")
      source_endpoint_key       = "source"
      target_endpoint_key       = "destination"
      tags                      = { Task = "MySQL-to-S3" }
    }
  }
}

# IAM Role for DMS to Access S3
resource "aws_iam_role" "dms_role" {
  name = "DMS-S3-Access-Role"

  assume_role_policy = jsonencode({
    Version   = "2008-10-17"
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "dms.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "dms_attach" {
  role       = aws_iam_role.dms_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}
