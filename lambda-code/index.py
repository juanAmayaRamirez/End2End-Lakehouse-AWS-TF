import boto3
import pymysql
import json
import os
import datetime

def lambda_handler(event, context):
    results = []
    username = os.environ['USERNAME']
    password = os.environ['PASSWORD']
    rds_host = os.environ['RDS_HOST']
    rds_port = int(os.environ['RDS_PORT'])
    database = os.environ['RDS_DATABASE']
    queries = event.get("queries", [])

    if not queries:
        return {
            "statusCode": 400,
            "body": json.dumps("Missing SQL query in the event payload.")
        }
    # Connect to RDS
    try:
        connection = pymysql.connect(
            host=rds_host,
            user=username,
            password=password,
            database=database, # if "CREATE DATABASE" not in query else None,
            port=rds_port,
            connect_timeout=10,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True  # Ensures queries run outside transactions
        )

        with connection.cursor() as cursor:
            for query in queries:
                cursor.execute(query)
                if query.strip().lower().startswith(("select", "show", "describe", "explain")):
                    result = cursor.fetchall()
                    for row in result:
                        for key, value in row.items():
                            if isinstance(value, (datetime.date, datetime.datetime)):  # Convert date fields
                                row[key] = value.strftime("%Y-%m-%d")

                    results.append({"query": query, "output": result})
                else:
                    connection.commit()  # Commit changes for INSERT, UPDATE, DELETE
                    results.append({"query": query, "output": "Query executed successfully."})

        return {
            "statusCode": 200,
            "body": results  # ✅ Returns output for all queries
        }

    except Exception as e:
        print(f"Database query error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(f"Failed to execute query: {str(e)}")
        }
    finally:
        if 'connection' in locals():
            connection.close()