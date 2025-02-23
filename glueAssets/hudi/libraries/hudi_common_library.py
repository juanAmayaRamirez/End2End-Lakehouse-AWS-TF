import boto3
import json
import datetime
from typing import Optional, Dict
from pyspark.sql import DataFrame
from pyspark.sql.functions import col, lit, to_timestamp, when
from botocore.exceptions import ClientError

def upsert_hudi_dataframe(
    spark_df: DataFrame,
    glue_database: str,
    table_name: str,
    target_path: str,
    table_type: str = "COPY_ON_WRITE",
    index_type: str = "BLOOM",
    enable_cleaner: bool = True,
    enable_hive_sync: bool = True,
    record_id: Optional[str] = None,
    ingestion_type: Optional[str] = None,
    precombine_key: Optional[str] = None,
    overwrite_precombine_key: bool = False,
    partition_key: Optional[str] = None,
    hudi_custom_options: Optional[Dict[str, str]] = None,
    method: str = "upsert",
) -> None:
    """
    Upserts a Spark DataFrame into a Hudi table.
    
    Args:
        spark_df (DataFrame): The DataFrame to upsert.
        glue_database (str): Glue database name.
        table_name (str): Hudi table name.
        target_path (str): Target path for the Hudi table.
        table_type (str): Hudi table type ("COPY_ON_WRITE" or "MERGE_ON_READ").
        index_type (str): Hudi index type ("BLOOM" or "GLOBAL_BLOOM").
        enable_cleaner (bool): Whether to enable automatic data cleaning.
        enable_hive_sync (bool): Whether to sync the table with Hive.
        record_id (Optional[str]): Primary key field name.
        ingestion_type (Optional[str]): Ingestion type ("cdc", "fl", or None).
        precombine_key (Optional[str]): Field used for precombine (default: timestamp if not provided).
        overwrite_precombine_key (bool): Whether to overwrite the precombine field.
        partition_key (Optional[str]): Partition key field.
        hudi_custom_options (Optional[Dict[str, str]]): Additional Hudi options.
        method (str): Write method (overwritten by ingestion_type if specified).
    """
    if not spark_df.columns:
        print(f"No records to write into {glue_database}.{table_name}")
        return
    
    print(f"Found records to write into {glue_database}.{table_name}")
    # Add a column to indicate deleted records for Hudi soft deletes
    if "Op" in spark_df.columns:
        spark_df = spark_df.withColumn('_hoodie_is_deleted', when(spark_df['Op'] == 'D', lit(True)).otherwise(lit(False)))

    # Define common Hudi settings
    hudi_options = {
        "className": "org.apache.hudi",
        "hoodie.table.name": table_name,
        "hoodie.datasource.write.table.type": table_type,
        "hoodie.datasource.write.operation": method,
        "hoodie.datasource.hive_sync.support_timestamp": "true",
        "path": target_path,
        "hoodie.index.type": index_type,
    }

    # Configure Hive sync if enabled
    if enable_hive_sync:
        hudi_options.update({
            "hoodie.datasource.hive_sync.enable": "true",
            "hoodie.datasource.hive_sync.database": glue_database,
            "hoodie.datasource.hive_sync.table": table_name,
            "hoodie.datasource.hive_sync.mode": "hms",
        })
    
    # Configure automatic cleaning if enabled
    if enable_cleaner:
        hudi_options.update({
            "hoodie.clean.automatic": "true",
            "hoodie.clean.async": "false",
            "hoodie.cleaner.policy": "KEEP_LATEST_COMMITS",
            "hoodie.cleaner.commits.retained": 10,
        })
    
    # Set up partitioning configuration
    if partition_key:
        hudi_options.update({
            "hoodie.datasource.write.partitionpath.field": partition_key,
            "hoodie.datasource.hive_sync.partition_fields": partition_key,
            "hoodie.datasource.write.hive_style_partitioning": "true",
            "hoodie.datasource.hive_sync.partition_extractor_class": "org.apache.hudi.hive.MultiPartKeysValueExtractor",
        })
    else:
        hudi_options.update({
            "hoodie.datasource.hive_sync.partition_extractor_class": "org.apache.hudi.hive.NonPartitionedExtractor",
            "hoodie.datasource.write.keygenerator.class": "org.apache.hudi.keygen.NonpartitionedKeyGenerator",
        })
    
    # Define precombine field (defaulting to a timestamp if not provided)
    precombine_field = precombine_key or "transaction_date_time"
    hudi_options["hoodie.datasource.write.precombine.field"] = precombine_field

    # Handle precombine key transformation
    if overwrite_precombine_key:
        spark_df = spark_df.withColumn(precombine_field, to_timestamp(col(precombine_key)))
    elif not precombine_key:
        spark_df = spark_df.withColumn(precombine_field, to_timestamp(lit(datetime.datetime.now())))
    
    # Merge additional custom Hudi options if provided
    if hudi_custom_options:
        hudi_options.update(hudi_custom_options)
    
    # Define record key field
    if record_id:
        hudi_options["hoodie.datasource.write.recordkey.field"] = record_id

    # Drop unnecessary columns before writing
    drop_columns = ['db', 'table_name', 'Op']
    spark_df = spark_df.drop(*drop_columns)

    # Handle ingestion types
    if ingestion_type == "cdc":
        try:
            boto3.client('glue').get_table(DatabaseName=glue_database, Name=table_name)
            print(f"{glue_database}.{table_name} exists. Starting CDC insert.")
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityNotFoundException':
                raise ValueError(f"{glue_database}.{table_name} does not exist. Run Full Load first.")
        hudi_options["hoodie.datasource.write.operation"] = "upsert"
        spark_df.write.format("hudi").options(**hudi_options).mode("Append").save()
    
    elif ingestion_type == "fl":
        hudi_options["hoodie.datasource.write.operation"] = "insert_overwrite_table"
        spark_df.write.format("hudi").options(**hudi_options).mode("Overwrite").save()
    
    else:
        spark_df.write.format("hudi").options(**hudi_options).mode("Append").save()


def load_mapping_config(bucket_name: str, mapping_file: str) -> Dict[str, str]:
    """
    Loads a mapping configuration file from an S3 bucket.
    
    Args:
        bucket_name (str): Name of the S3 bucket.
        mapping_file (str): Path to the mapping file.
    
    Returns:
        dict: Dictionary containing mapping keys (primary_key, partition_key, precombine_key).
    """
    s3_client = boto3.client("s3")
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=mapping_file)
        return json.loads(response["Body"].read().decode("utf-8"))
    except s3_client.exceptions.NoSuchKey:
        raise FileNotFoundError(f"The file {mapping_file} does not exist in {bucket_name}")
