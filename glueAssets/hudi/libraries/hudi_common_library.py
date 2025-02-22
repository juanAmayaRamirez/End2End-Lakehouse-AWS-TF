# LIBRERIA PARA  FACILITAR LA EJECUCION EN GLUE DE LA TRANSFORMACION DE DATOS
import boto3, json, datetime
from typing import Optional
from awsglue.context import GlueContext, DynamicFrame
from awsglue.utils import getResolvedOptions
from pyspark.sql.functions import col, lit, to_timestamp, desc, dense_rank, when
from pyspark.sql.window import Window
from pyspark.sql import DataFrame
from botocore.exceptions import ClientError
from dataclasses import dataclass
import re
import ast
import sys

args = getResolvedOptions(sys.argv, ['JOB_NAME'])

class NotFormatFoundError(Exception):
    pass
class AWSS3(object):
    """Helper class to which add functionality on top of boto3 """

    def __init__(self, bucket):

        self.BucketName = bucket
        self.client = boto3.client("s3")

    def put_files(self, Response=None, Key=None):
        """
        Put the File on S3
        :return: Bool
        """
        try:
            response = self.client.put_object(
                Body=Response, Bucket=self.BucketName, Key=Key
            )
            return "ok"
        except Exception as e:
            raise Exception("Error : {} ".format(e))

    def item_exists(self, Key):
        """Given key check if the items exists on AWS S3 """
        try:
            response_new = self.client.get_object(Bucket=self.BucketName, Key=str(Key))
            return True
        except Exception as e:
            return False

    def get_item(self, Key):

        """Gets the Bytes Data from AWS S3 """

        try:
            response_new = self.client.get_object(Bucket=self.BucketName, Key=str(Key))
            return response_new["Body"].read()

        except Exception as e:
            print("Error :{}".format(e))
            return False

    def find_one_update(self, data=None, key=None):

        """
        This checks if Key is on S3 if it is return the data from s3
        else store on s3 and return it
        """

        flag = self.item_exists(Key=key)

        if flag:
            data = self.get_item(Key=key)
            return data

        else:
            self.put_files(Key=key, Response=data)
            return data

    def delete_object(self, Key):

        response = self.client.delete_object(Bucket=self.BucketName, Key=Key, )
        return response

    def get_all_keys(self, Prefix=""):

        """
        :param Prefix: Prefix string
        :return: Keys List
        """
        try:
            paginator = self.client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.BucketName, Prefix=Prefix)

            tmp = []

            for page in pages:
                for obj in page["Contents"]:
                    tmp.append(obj["Key"])

            return tmp
        except Exception as e:
            return []

    def print_tree(self):
        keys = self.get_all_keys()
        for key in keys:
            print(key)
        return None

    def find_one_similar_key(self, searchTerm=""):
        keys = self.get_all_keys()
        return [key for key in keys if re.search(searchTerm, key)]

    def __repr__(self):
        return "AWS S3 Helper class "


@dataclass
class HUDISettings:
    """Class for keeping track of an item in inventory."""

    table_name: str
    path: str


class HUDIIncrementalReader(AWSS3):
    def __init__(self, bucket, hudi_settings, spark_session):
        AWSS3.__init__(self, bucket=bucket)
        if type(hudi_settings).__name__ != "HUDISettings": raise Exception("please pass correct settings ")
        self.hudi_settings = hudi_settings
        self.spark = spark_session

    def __check_meta_data_file(self):
        """
        check if metadata for table exists
        :return: Bool
        """
        file_name = f"metadata/{args['JOB_NAME']}/{self.hudi_settings.table_name}.json"
        return self.item_exists(Key=file_name)

    def clean_check_point(self):
        file_name = f"metadata/{args['JOB_NAME']}/{self.hudi_settings.table_name}.json"
        self.delete_object(Key=file_name)

    def __read_meta_data(self):
        file_name = f"metadata/{args['JOB_NAME']}/{self.hudi_settings.table_name}.json"

        return ast.literal_eval(self.get_item(Key=file_name).decode("utf-8"))

    def __push_meta_data(self, json_data):
        file_name = f"metadata/{args['JOB_NAME']}/{self.hudi_settings.table_name}.json"
        self.put_files(
            Key=file_name, Response=json.dumps(json_data)
        )

    def __get_begin_commit(self):
        self.spark.read.format("hudi").load(self.hudi_settings.path).createOrReplaceTempView("hudi_snapshot")
        commits = list(map(lambda row: row[0], self.spark.sql(
            "select distinct(_hoodie_commit_time) as commitTime from  hudi_snapshot order by commitTime asc").limit(
            50).collect()))

        """begin from start """
        begin_time = int(commits[0]) - 1
        return begin_time

    def __read_inc_data(self, commit_time):
        incremental_read_options = {
            'hoodie.datasource.query.type': 'incremental',
            'hoodie.datasource.read.begin.instanttime': commit_time,
        }
        incremental_df = self.spark.read.format("hudi").options(**incremental_read_options).load(
            self.hudi_settings.path).createOrReplaceTempView("hudi_incremental")

        df = self.spark.sql("select * from  hudi_incremental")

        return df

    def __get_last_commit(self):
        commits = list(map(lambda row: row[0], self.spark.sql(
            "select distinct(_hoodie_commit_time) as commitTime from  hudi_incremental order by commitTime asc").limit(
            50).collect()))
        last_commit = commits[len(commits) - 1]
        return last_commit

    def __run(self):
        """Check the metadata file"""
        flag = self.__check_meta_data_file()

        """if metadata files exists load the last commit and start inc loading from that commit """
        if flag:
            meta_data = json.loads(self.__read_meta_data())
            print(f"""
            ******************LOGS******************
            meta_data {meta_data}
            last_processed_commit : {meta_data.get("last_processed_commit")}
            ***************************************
            """)

            read_commit = str(meta_data.get("last_processed_commit"))
            df = self.__read_inc_data(commit_time=read_commit)

            """if there is no INC data then it return Empty DF """
            if not df.rdd.isEmpty():
                last_commit = self.__get_last_commit()
                self.__push_meta_data(json_data=json.dumps({
                    "last_processed_commit": last_commit,
                    "table_name": self.hudi_settings.table_name,
                    "path": self.hudi_settings.path,
                    "inserted_time": datetime.datetime.now().__str__(),

                }))
                return df
            else:
                return df

        else:

            """Metadata files does not exists meaning we need to create  metadata file on S3 and start reading from begining commit"""

            read_commit = self.__get_begin_commit()

            df = self.__read_inc_data(commit_time=read_commit)
            last_commit = self.__get_last_commit()

            self.__push_meta_data(json_data=json.dumps({
                "last_processed_commit": last_commit,
                "table_name": self.hudi_settings.table_name,
                "path": self.hudi_settings.path,
                "inserted_time": datetime.datetime.now().__str__(),

            }))

            return df

    def read(self):
        """
        reads INC data and return Spark Df
        :return:
        """

        return self.__run()


def read_data_2(spark,
                glueContext: GlueContext,
                s3_url: str,
                data_type: str,
                table_name: str,
                ingestion_type: Optional[str] = None,
                ) -> DynamicFrame:
    """
    Reads data from an S3 bucket using AWS Glue and returns a Spark DataFrame.

    Args:
        glueContext: Contexto glue del job.
        s3_url (str): S3 bucket path where data is stored
        data_type (str): file format of the data (e.g., parquet, csv, json, hudi)
        table_name (str): name of glue table
        ingestion_type (str) tipo de ingesta en caso de usar dms (cdc, fl, inc)(Default = None) [OPCIONAL]
    Returns:
        spark_df (pyspark.sql.DataFrame): Spark DataFrame containing the data
    """
    if ingestion_type is None:
        print("Reading all objects at the specified path recursivelly")
        exclussions = ""
    elif ingestion_type == "cdc":
        print(f"Reading only '{ingestion_type}' objects at the specified path recursivelly")
        exclussions= "[\"**/LOAD*\",\"**/SEGMENT*\"]"
    elif ingestion_type == "fl":
        print(f"Reading only '{ingestion_type}' objects at the specified path recursivelly")
        exclussions= "[\"**/2*\"]"
    else:
        raise ValueError("Invalid ingestion type. Allowed values are 'cdc' and 'fl'.")

    dyf = None
    transformation_ctx = f"S3bucket_{table_name}"
    if data_type == 'parquet':
        dyf = glueContext.create_dynamic_frame.from_options(
            connection_type="s3",
            connection_options={
                "paths": [s3_url],
                "groupFiles": "none",
                "recurse": True,
                "exclusions": exclussions,
            },
            format="parquet",
            format_options={"withHeader":True},
            transformation_ctx=transformation_ctx,
        )
    elif data_type == 'csv':
        dyf = glueContext.create_dynamic_frame.from_options(
            connection_type="s3",
            connection_options={
                "paths": [s3_url],
                "groupFiles": "none",
                "recurse": True,
                "exclusions": exclussions,
            },
            format="csv",
            format_options={
                "quoteChar": '"',
                "withHeader": True,
                "separator": ",",
                "optimizePerformance": False,
            },
            transformation_ctx=transformation_ctx,            
        )
    elif data_type == 'json':
        dyf = glueContext.create_dynamic_frame.from_options(
            connection_type="s3",
            connection_options={
                "paths": [s3_url],
                "groupFiles": "none",
                "recurse": True,
                "exclusions": exclussions,
            },
            format=data_type,
            format_options={
                            "jsonPath": "$.id",
                            "multiline": True,
                            # "optimizePerformance": True, -> not compatible with jsonPath, multiline
            },
            transformation_ctx=transformation_ctx,
        )
    elif data_type == "hudi":
        df = spark.read.format(data_type).load(s3_url)
        dyf = DynamicFrame.fromDF(df, glueContext, transformation_ctx)
    else:
        raise NotFormatFoundError()
    
    return dyf

def upsert_hudi_table_0_14_1(
                     spark_dyf: DynamicFrame,
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
        "hoodie.clean.async": "true",
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

    if spark_dyf.count() > 0:
        print(f'Total record count to write into {glue_database}.{table_name} = {str(spark_dyf.count())}')
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
            spark_df = spark_dyf.toDF().withColumn(precomb_field, to_timestamp(col(precomb_key)))
        else:
            precomb_field = "transaction_date_time"
            hudi_final_settings["hoodie.datasource.write.precombine.field"] = precomb_field
            spark_df = spark_dyf.toDF().withColumn(precomb_field, col(precomb_key)).drop(precomb_key)
    else:
        precomb_field = "transaction_date_time"
        hudi_final_settings["hoodie.datasource.write.precombine.field"] = precomb_field
        spark_df = spark_dyf.toDF().withColumn(precomb_field, to_timestamp(lit(datetime.datetime.now())))
    
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
        if record_id is None:
            raise BaseException(f'error record_id CANNOT be None for ingestion_type "cdc" {glue_database}.{table_name}. Change ingestion_type to fl OR do not use ingestion_type')
        record_id_list = record_id.split(",")
        w = Window.partitionBy(*record_id_list).orderBy(desc(precomb_field))
        spark_df = spark_df.withColumn('Rank',dense_rank().over(w))
        spark_df = spark_df.filter(spark_df.Rank == 1).drop(spark_df.Rank)
        # spark_df=transformations(spark_df)
        spark_u_df = spark_df.filter("Op != 'D'").drop(*dropColumnList)
        spark_d_df = spark_df.filter("Op = 'D'").drop(*dropColumnList)

        if spark_u_df.count() > 0:
            spark_u_df.write.format('hudi').options(**hudi_final_settings).mode('Append').save()
        if spark_d_df.count() > 0:
            hudi_final_settings = {**hudi_final_settings, **deleteDataConfig}
            spark_d_df.write.format('hudi').options(**hudi_final_settings).mode('Append').save()

    elif ingestion_type == "fl":
        hudi_final_settings["hoodie.datasource.write.operation"] = "insert_overwrite_table"
        spark_df = spark_df.drop(*dropColumnList)
        spark_df.write.format('hudi').options(**hudi_final_settings).mode('Overwrite').save()

    elif ingestion_type is None:
        spark_df.write.format('hudi').options(**hudi_final_settings).mode('Append').save()
    else:
        raise ValueError(f"{ingestion_type} not found it must be either fl, cdc or None")

def upsert_hudi_dataframe_0_14_1(
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
