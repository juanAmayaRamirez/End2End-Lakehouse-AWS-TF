# Terraform Lakehouse Infrastructure as Code (IaC)

## Overview
This repository provides an educational example of how to build an **end-to-end lakehouse architecture** using **Terraform**. The infrastructure includes:

- **Three-tier S3 bucket architecture** (Bronze, Silver, and Gold)
- **Amazon RDS (MySQL)** as the source database
- **AWS Database Migration Service (DMS)** for ingesting changes into S3
- **AWS Glue** for data processing and managing Apache Hudi tables
- **Networking components** including a VPC, subnets, and security groups
- **IAM roles and permissions** for managing resource access
- **Lambda function** to assist with table creation in AWS Glue

> ⚠ **Note:** This repository is **not production-ready** and should be used for **educational purposes** only.

## Architecture
```
 +------------------------+
 |      Source DB         |
 |      (MySQL)           |
 +------------------------+
          |
          |  (CDC Replication)
          v
 +------------------------+
 |         DMS            |
 | (Change Data Capture)  |
 +------------------------+
          |
          v
 +------------------------+
 |     S3 Buckets         |
 | (Bronze, Silver, Gold) |
 +------------------------+
          |
          v
 +------------------------+
 |        Glue            |
 | (ETL with Hudi)        |
 +------------------------+
```

## Prerequisites
Before using this Terraform project, ensure you have:

- [Terraform](https://developer.hashicorp.com/terraform/tutorials/aws-get-started/install-cli) installed
- AWS CLI configured with necessary permissions
- `make` installed to execute the provided **Makefile**
- if you do not have make just run terraform commands

## Setup and Usage
### 1. Initialize Terraform
Run the following command to initialize Terraform with an S3 backend:
```sh
make init ENV=dev
```

### 2. Plan Changes
Check the infrastructure changes before applying:
```sh
make plan ENV=dev
```

### 3. Apply Changes
Deploy the infrastructure:
```sh
make apply
```

### 4. View Current State
To display the current Terraform state:
```sh
make show
```

### 5. mock Data setup Configuration
Run the Lambda function with `initial_configuration.json` as the payload. This step creates a sample schema, tables, and initial data in RDS, which AWS DMS will then ingest into the data lake.

### 6. Run DMS Task
After setting up the initial schema and data, start the AWS DMS task to migrate data from RDS to S3.

### 7. Apply upserts
To test change data capture (CDC), run the Lambda function again with `apply_upserts.json`. This applies updates to the RDS database, allowing you to observe how AWS DMS captures the changes and applies them to S3 in Parquet format.

### 8. Verify data on S3
To test change data capture (CDC), run the Lambda function again with `apply_upserts.json`. This applies updates to the RDS database, allowing you to observe how AWS DMS captures the changes and applies them to S3 in Parquet format.

### 9. Destroy Infrastructure
To delete the deployed infrastructure:
```sh
make destroy ENV=dev
```

## Components
### **S3 Data Lake (Bronze, Silver, Gold)**
- **Bronze:** Raw data from source systems (RDS via DMS)
- **Silver:** Cleaned and transformed data
- **Gold:** Final aggregated tables for analytics

### **Amazon RDS (MySQL)**
- Used as the source database for transactional data
- Configured with **binlog format** for Change Data Capture (CDC)

### **AWS DMS (Database Migration Service)**
- Captures changes from MySQL and writes them to S3 in **Parquet format**
- Uses a replication instance to process data migrations

### **AWS Glue & Apache Hudi**
- AWS Glue jobs process data from **Bronze → Silver → Gold**
- **Apache Hudi** enables incremental updates and time-travel queries

### **Networking & Security**
- **VPC with subnets** for RDS, DMS, and Glue
- **Security Groups** control access between services

## Makefile
This repository includes a `Makefile` to simplify common Terraform commands:
```sh
.PHONY: validate init plan apply show graph destroy

.DEFAULT_GOAL := validate

validate:     # Format and validate Terraform files
init:         # Initialize Terraform with S3 backend
plan:         # Show execution plan
apply:        # Apply Terraform changes
show:         # Display current state
graph:        # Generate dependency graph
```

## Limitations & Future Improvements
- **Not production-ready:** No monitoring, alerting, or fine-grained IAM policies
- **Manual credentials:** Secrets like database passwords should be managed using AWS Secrets Manager
- **Limited HA:** The architecture does not support high availability configurations

## References
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [AWS Glue & Apache Hudi](https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-format-hudi.html)
- [AWS DMS Documentation](https://docs.aws.amazon.com/dms/latest/userguide/Welcome.html)

---
**Author:** This repository was created to help Data Engineers understand **Lakehouse architectures** on AWS using Terraform.

