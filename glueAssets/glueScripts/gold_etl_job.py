import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.dynamicframe import DynamicFrame
from awsglue import DynamicFrame
from pyspark.sql import functions as SqlFuncs

def sparkAggregate(glueContext, parentFrame, groups, aggs, transformation_ctx) -> DynamicFrame:
    aggsFuncs = []
    for column, func in aggs:
        aggsFuncs.append(getattr(SqlFuncs, func)(column))
    result = parentFrame.toDF().groupBy(*groups).agg(*aggsFuncs) if len(groups) > 0 else parentFrame.toDF().agg(*aggsFuncs)
    return DynamicFrame.fromDF(result, glueContext, transformation_ctx)

args = getResolvedOptions(sys.argv, ['JOB_NAME'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

# Script generated for node AWS Glue Data Catalog
AWSGlueDataCatalog_node1740065307772_df = glueContext.create_data_frame.from_catalog(database="lakehouse_db", table_name="aws_certifications_certifications_awarded")
AWSGlueDataCatalog_node1740065307772 = DynamicFrame.fromDF(AWSGlueDataCatalog_node1740065307772_df, glueContext, "AWSGlueDataCatalog_node1740065307772")

# Script generated for node AWS Glue Data Catalog
AWSGlueDataCatalog_node1740065495484_df = glueContext.create_data_frame.from_catalog(database="lakehouse_db", table_name="aws_certifications_users")
AWSGlueDataCatalog_node1740065495484 = DynamicFrame.fromDF(AWSGlueDataCatalog_node1740065495484_df, glueContext, "AWSGlueDataCatalog_node1740065495484")

# Script generated for node Aggregate
Aggregate_node1740065392272 = sparkAggregate(glueContext, parentFrame = AWSGlueDataCatalog_node1740065307772, groups = ["user_id"], aggs = [["certification_id", "count"], ["awarded_date", "max"]], transformation_ctx = "Aggregate_node1740065392272")

# Script generated for node Join
Join_node1740065535475 = Join.apply(frame1=Aggregate_node1740065392272, frame2=AWSGlueDataCatalog_node1740065495484, keys1=["user_id"], keys2=["user_id"], transformation_ctx="Join_node1740065535475")

# Script generated for node Change Schema
ChangeSchema_node1740065708106 = ApplyMapping.apply(frame=Join_node1740065535475, mappings=[("`count(certification_id)`", "long", "certifications_awarded", "long"), ("`max(awarded_date)`", "date", "last_awarded_certification", "date"), ("name", "string", "name", "string")], transformation_ctx="ChangeSchema_node1740065708106")

# Script generated for node Amazon S3
AmazonS3_node1740065800166 = glueContext.getSink(path="s3://my-gold-bucket-381492178679/user_certification_count/", connection_type="s3", updateBehavior="UPDATE_IN_DATABASE", partitionKeys=[], enableUpdateCatalog=True, transformation_ctx="AmazonS3_node1740065800166")
AmazonS3_node1740065800166.setCatalogInfo(catalogDatabase="lakehouse_db",catalogTableName="user_certification_count")
AmazonS3_node1740065800166.setFormat("glueparquet", compression="snappy")
AmazonS3_node1740065800166.writeFrame(ChangeSchema_node1740065708106)
job.commit()