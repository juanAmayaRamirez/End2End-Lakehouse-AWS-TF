from pyspark.sql.types import StringType
from pyspark.sql.session import SparkSession
from pyspark.sql.functions import col, when, trim
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.dynamicframe import DynamicFrame
import boto3, sys, re
import hudi_common_library as gl2

args = getResolvedOptions(sys.argv, ['JOB_NAME'])

spark = SparkSession.builder.config('spark.serializer','org.apache.spark.serializer.KryoSerializer')\
    .config('spark.sql.hive.convertMetastoreParquet', 'false')\
    .config("spark.sql.parquet.datetimeRebaseModeInRead", "CORRECTED")\
    .config("spark.sql.avro.datetimeRebaseModeInWrite", "CORRECTED")\
    .getOrCreate()

glueContext = GlueContext(spark.sparkContext)
job = Job(glueContext)
job.init(args['JOB_NAME'], args)
logger = glueContext.get_logger()

dbName = 'lakehouse_db'


# Get source tables
mapping_tables = [
    ('aws_certifications' , 'certifications_awarded'),
    ('aws_certifications' , 'certifications'),
    ('aws_certifications' , 'users')
]

# Iterate over the list of tuples
for sourceSchemaName, sourceTableName in mapping_tables:
    print(f"Schema: {sourceSchemaName}, Table: {sourceTableName}")
    targetTableName = f"{sourceSchemaName}_{sourceTableName}"
    targetTableName = re.sub(r'[^1-9a-zA-Z_]', '_', targetTableName)
    sourceS3TablePath = f's3://my-bronce-bucket-381492178679/rds/{sourceSchemaName}/{sourceTableName}/'
    targetS3TablePath = f's3://my-silver-bucket-381492178679/rds/{sourceSchemaName}/{sourceTableName}/'
    
    # 1. read data from origin
    logger.info(f'read table {sourceSchemaName}.{sourceTableName} from s3 path {sourceS3TablePath}')
    dyf = glueContext.create_dynamic_frame.from_options(
        connection_type="s3",
        connection_options={
            "paths": [sourceS3TablePath],
            "groupFiles": "none",
            "recurse": True,
            "exclusions": "[\"**/LOAD*\",\"**/SEGMENT*\"]",
        },
        format="parquet",
        format_options={"withHeader":True},
        transformation_ctx=targetTableName,
    )
    print(f'sourcename: {sourceSchemaName},sourceTableName: {sourceTableName}')
    
    # 2. load primary key configs
    if sourceTableName == 'certifications_awarded':
        primary_key = 'awarded_id'
    elif sourceTableName == 'certifications':
        primary_key = 'certification_id'
    elif sourceTableName == 'users':
        primary_key = 'user_id'

    # 3. upsert hudi table. 
    logger.info(f'upserting hudi table {dbName}.{targetTableName} in s3 path {targetS3TablePath}')
    
    print("##########################")
    print("dbname: ", dbName)
    print("table_name: ", targetTableName)
    print("primarykey: ", primary_key)
    print("targetpath: ", targetS3TablePath)
    print("SCHEMA: ")
    df = dyf.toDF()
    df.printSchema()
    print("##########################")
    gl2.upsert_hudi_dataframe(
        spark_df = df,
        glue_database = dbName,
        table_name = targetTableName.lower(),
        record_id = primary_key,
        precombine_key = "ts",
        target_path = targetS3TablePath,
        ingestion_type = "cdc",
        hudi_custom_options = {
            **{
                "hoodie.datasource.write.payload.class":"org.apache.hudi.common.model.DefaultHoodieRecordPayload",
                "hoodie.payload.ordering.field" : "ts"
            }
        }
    )
job.commit()