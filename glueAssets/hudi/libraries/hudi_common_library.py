# LIBRERIA PARA  FACILITAR LA EJECUCION EN GLUE DE LA TRANSFORMACION DE DATOS
import boto3, json, datetime
from typing import Optional
from pyspark.sql.functions import col, lit, to_timestamp, when
from pyspark.sql import DataFrame
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
                     precomb_key: Optional[str] = None,
                     overwrite_precomb_key: bool = False,
                     partition_key: Optional[str] = None,
                     hudi_custom_options: Optional[dict] = None,
                     method: str = "upsert",
                     ):
    """
    Upserts a DynamicFrame into a Hudi table.

    Args:
        spark_dyf (DynamicFrame): The DynamicFrame to upsert.
        glue_database (str): The name of the glue database.
        table_name (str): The name of the Hudi table.
        record_id (str): The name of the field in the dataframe that will be used as the record key, usually primary key in SQL DB.
        target_path (str): The path to the target Hudi table.
        table_type (str): The Hudi table type (COPY_ON_WRITE, MERGE_ON_READ)(Default = 'COPY_ON_WRITE') [OPCIONAL].
        index_type (str): hudi index type to use (BLOOM, GLOBAL_BLOOM)(Default = 'BLOOM') [OPCIONAL].
        enable_cleaner (bool): Whether or not to enable data cleaning (Default = True) [OPCIONAL].
        enable_hive_sync (bool): Whether or not to enable syncing with Hive (Default = True) [OPCIONAL].
        ingestion_type (str): ingestion type when using dms, table will be writen as is (cdc, fl)(Default = None) [OPCIONAL]
        precomb_key (str): transaccion field that will be used by hudi, if not specified current timestamp will be used (Default = None) [OPCIONAL].
        overwrite_precomb_key (bool): whether or not to overwrite the precomb_key (transaction_date_time) with the value specified in precomb_key arg (Default = False) [OPCIONAL].
        partition_key (str): partition key field that will be used to partition data in <partition>=<partition_value> format, if not specified data partitioning is dissabled (Default = None) [OPCIONAL].
        hudi_custom_options (dict): additional hudi options as key value pairs, to add or overwrite existing options (Default = None) [OPCIONAL].
        method (str): The Hudi write method to use, if using cdc or fl it will be overwriten to 'upsert' or 'insert_overwrite' correspondingly (default = 'upsert') [OPCIONAL].
    Returns:
        None
    """ 

    # These settings common to all data writes
    hudi_common_settings = {
        'className' : 'org.apache.hudi', 
        "hoodie.table.name": table_name,
        "hoodie.datasource.write.table.type": table_type,
        "hoodie.datasource.write.operation": method,
        "hoodie.datasource.hive_sync.support_timestamp": "true",
        "path" : target_path
    }

    # These settings enable syncing with Hive
    hudi_hive_sync_settings = {
        "hoodie.parquet.compression.codec": "snappy",
        "hoodie.datasource.hive_sync.enable": "true",
        "hoodie.datasource.hive_sync.database": glue_database,
        "hoodie.datasource.hive_sync.table": table_name,
        "hoodie.datasource.hive_sync.use_jdbc": "false",
        "hoodie.datasource.hive_sync.mode": "hms",
    }

    hudi_mor_compation_settings = {
        'hoodie.compact.inline': 'false', 
        'hoodie.compact.inline.max.delta.commits': 20, 
        'hoodie.parquet.small.file.limit': 0
    }

    # These settings enable automatic cleaning of old data
    hudi_cleaner_options = {
        "hoodie.clean.automatic": "true",
        "hoodie.clean.async": "false",
        "hoodie.cleaner.policy": 'KEEP_LATEST_COMMITS',
        'hoodie.cleaner.commits.retained': 10,
        "hoodie-conf hoodie.cleaner.parallelism": '200',
    }

    # These settings enable partitioning of the data
    partition_settings = {
        "hoodie.datasource.write.partitionpath.field": partition_key,
        "hoodie.datasource.hive_sync.partition_fields": partition_key,
        "hoodie.datasource.write.hive_style_partitioning": "true",
        "hoodie.datasource.hive_sync.partition_extractor_class": "org.apache.hudi.hive.MultiPartKeysValueExtractor",
    }
    # These settings are for un partitioned data
    unpartition_settings = {
        'hoodie.datasource.hive_sync.partition_extractor_class': 'org.apache.hudi.hive.NonPartitionedExtractor', 
        'hoodie.datasource.write.keygenerator.class': 'org.apache.hudi.keygen.NonpartitionedKeyGenerator',
    }

    # Define a dictionary with the index settings for Hudi
    hudi_index_settings = {
        "hoodie.index.type": index_type,  # Specify the index type for Hudi
    }

    deleteDataConfig = {
        'hoodie.datasource.write.payload.class': 'org.apache.hudi.common.model.EmptyHoodieRecordPayload'
    }

    dropColumnList = ['db','table_name','Op']
    hudi_final_settings = {**hudi_common_settings, **hudi_index_settings}

    if len(spark_df.columns) > 0:
        print(f'Found records to write into {glue_database}.{table_name}')
        spark_df = spark_df.withColumn('_hoodie_is_deleted', when(spark_df['Op'] == 'D', lit(True)).otherwise(lit(False)))
        
    else:
        print(f"There are no records to write into {glue_database}.{table_name}")
        return

    if table_type == "MERGE_ON_READ":
        print(f"writing as {table_type} hudi table")
        hudi_final_settings = {**hudi_final_settings, **hudi_mor_compation_settings}
    elif table_type == "COPY_ON_WRITE":
        print(f"writing as {table_type} hudi table")
    else:
        raise ValueError(f"{table_type} not found it must be either 'MERGE_ON_READ', or 'COPY_ON_WRITE'")
    
    if enable_hive_sync:
        hudi_final_settings = {**hudi_final_settings,**hudi_hive_sync_settings}

    if enable_cleaner:
        hudi_final_settings = {**hudi_final_settings,**hudi_cleaner_options}

    if partition_key is not None:
        hudi_final_settings = {**hudi_final_settings,**partition_settings}
    else:
        hudi_final_settings = {**hudi_final_settings,**unpartition_settings}

    if precomb_key is not None:
        if overwrite_precomb_key:
            precomb_field = precomb_key
            hudi_final_settings["hoodie.datasource.write.precombine.field"] = precomb_field
            spark_df = spark_df.withColumn(precomb_field, to_timestamp(col(precomb_key)))
        else:
            precomb_field = "transaction_date_time"
            hudi_final_settings["hoodie.datasource.write.precombine.field"] = precomb_field
            spark_df = spark_df.withColumn(precomb_field, col(precomb_key)).drop(precomb_key)
    else:
        precomb_field = "transaction_date_time"
        hudi_final_settings["hoodie.datasource.write.precombine.field"] = precomb_field
        spark_df = spark_df.withColumn(precomb_field, to_timestamp(lit(datetime.datetime.now())))
    
    if hudi_custom_options is not None:
        for key, value in hudi_custom_options.items():
            hudi_final_settings[key] = value

    if record_id is not None:
        hudi_final_settings["hoodie.datasource.write.recordkey.field"] = record_id
    
    if ingestion_type == "cdc":
        try:
            glueClient = boto3.client('glue')
            glueClient.get_table(DatabaseName=glue_database,Name=table_name)
            print(f'{glue_database}.{table_name} exists starting cdc insert')
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityNotFoundException':
                raise BaseException(f'{glue_database}.{table_name} does not exist. Run Full Load First.')

        hudi_final_settings["hoodie.datasource.write.operation"] = "upsert"
        # if record_id is None:
        #     # raise BaseException(f'error record_id CANNOT be None for ingestion_type "cdc" {glue_database}.{table_name}. Change ingestion_type to fl OR do not use ingestion_type')
        #     record_id_list = record_id.split(",")
        #     w = Window.partitionBy(*record_id_list).orderBy(desc(precomb_field))
        #     spark_df = spark_df.withColumn('Rank',dense_rank().over(w))
        #     spark_df = spark_df.filter(spark_df.Rank == 1).drop(spark_df.Rank)
        spark_df = spark_df.drop(*dropColumnList)
        spark_df.write.format('hudi').options(**hudi_final_settings).mode('Append').save()

    elif ingestion_type == "fl":
        hudi_final_settings["hoodie.datasource.write.operation"] = "insert_overwrite_table"
        spark_df = spark_df.drop(*dropColumnList)
        spark_df.write.format('hudi').options(**hudi_final_settings).mode('Overwrite').save()

    elif ingestion_type is None:
        spark_df.write.format('hudi').options(**hudi_final_settings).mode('Append').save()
    else:
        raise ValueError(f"{ingestion_type} not found it must be either fl, cdc or None")

def load_mapping_config(bucket_name : str,
                        mapping_file: str) -> dict:
    """
    Loads Mapping config according to an s3 bucket and mapping file.

    Args:
        bucket_name (str): s3 bucket name where mapping_file is located.
        mapping_file (str): mapping_file json object path, (Example: path/to/mappings/mapping_table.json).
    Returns:
        mapping_keys (dict): dictionary with mapping keys (primary_key, partition_key, precomb_key)
    """ 
    s3Client = boto3.client('s3')
    try:
        response = s3Client.get_object(
            Bucket=bucket_name, 
            Key= mapping_file
        )
        mapping_keys = json.loads(response['Body'].read().decode('utf-8'))
    
    except s3Client.exceptions.NoSuchKey:
        raise Exception(f"the file {mapping_file} does not exist in {bucket_name}")
    
    return mapping_keys
