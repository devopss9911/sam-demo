import pymysql
import pymysql.cursors
import os
import boto3 as aws
from boto3.dynamodb.conditions import Key
import time
from datetime import datetime, timedelta
import json
from decimal import Decimal

# -------------------------------------------------------------------------------------------------
# Call DB Events on Aurora [David Thomas - 1 Apr 2022]
# -------------------------------------------------------------------------------------------------
def callDB(event, connection):
    try:
        conn = pymysql.connect(host=connection['rds_host'], user=connection['user_name'], passwd=connection['password'], db=connection['db_name'], cursorclass=pymysql.cursors.DictCursor)

        # build query
        dbo = event["dbo"]
        event.pop("dbo")

        params = ""
        for item in event:
            params = params + sanitize_field_value(str(event[item])) + ","

        params = params[0:len(params) - 1]

        with conn.cursor() as cursor:
            query = "call pr_" + dbo + "(" + params + ")"
            cursor.execute(query)
            result = cursor.fetchall()

            return result
    except Exception as err:
        print("error with crud: ", err)


# -------------------------------------------------------------------------------------------------
# Sanatize field value [David Thomas - 1 Apr 2022]
# -------------------------------------------------------------------------------------------------
def sanitize_field_value(value):
    if value == "None" or value == None:
        return "null"

    if len(value) > 1 and "'" in value:
        value = value.strip("'")
        value = value.replace("'", "''")

    if not value.startswith("'"):
        value = "'" + value
    if not value.endswith("'"):
        value = value + "'"
    if value == "'":
        value = "''"

    return value


# -------------------------------------------------------------------------------------------------
# Get Dynamo by pk_sk [Denver Naidoo - 11 May 2022]
# -------------------------------------------------------------------------------------------------
def get_dynamo_by_pk_sk(payload):
    dynamodb = aws.resource("dynamodb")
    table = dynamodb.Table(os.environ.get("DynamoMarketplace"))
    try:
        result_set = [{}]
        key = {}
        key["pk"] = payload["pk"]
        key["sk"] = payload["sk"]
        column_list = []
        response = table.get_item(
            Key=key,
        )
        result_set = response
        if len(result_set) > 0:
            if "Item" in result_set:
                result_set = response["Item"]
                if "ColumnList" in payload:
                    column_list.append(payload["ColumnList"])
                    for column in column_list:
                        if column in result_set:
                            result_set[column] = response["Item"][column]
            else:
                result_set = {}
        return result_set
    except Exception as e:
        print(f"get_dynamo_by_pk_sk() => #EXCEPTION: {format(e)}")
        return {"statusCode": 403, "status": "FAILED"}


# -------------------------------------------------------------------------------------------------
# Get Dynamo by pk_sk [Denver Naidoo - 11 May 2022]
# -------------------------------------------------------------------------------------------------
def update_dynamo(payload):
    dynamodb = aws.resource("dynamodb")
    table = dynamodb.Table(os.environ.get("DynamoMarketplace"))
    return_value = {}
    try:
        payload = json.loads(json.dumps(payload, default=str))
        payload = json.loads(json.dumps(payload), parse_float=Decimal)
        update_expression = "set"
        expression_attribute_values = {}
        if "lsi_id3" not in payload:
            payload["lsi_id3"] = time.time_ns()
        if "UTCDateCreated" not in payload:
            payload["UTCDateCreated"] = str(datetime.now())
        payload["UTCDateUpdated"] = str(datetime.now())
        for attribute in payload:
            if attribute not in ["pk", "sk"]:
                update_expression = f"{update_expression} {attribute}=:{attribute},"
                dict_key = f":{attribute}"
                expression_attribute_values[dict_key] = payload[attribute]
        if update_expression[-1] == ",":
            update_expression = update_expression[:-1]
        response = table.update_item(
            Key={"pk": payload["pk"], "sk": payload["sk"]},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW",
        )
        return_value["HTTPStatusCode"] = response["ResponseMetadata"]["HTTPStatusCode"]
        return return_value
    except Exception as e:
        print(f"update_dynamo() => #EXCEPTION: {format(e)}")
        return {"statusCode": 403, "status": "FAILED"}


# -------------------------------------------------------------------------------------------------
# Get the record by pk and filter by lsi condition [Denver Naidoo -11 May 2022]
# -------------------------------------------------------------------------------------------------
def get_dynamo_by_pk_lsi_condition(payload):
    dynamodb = aws.resource("dynamodb")
    table = dynamodb.Table(os.environ.get("DynamoMarketplace"))
    try:
        result_set = [{}]
        sort_key_date_conversion = False
        index_name = payload["lsi_name"]
        lsi_value = payload["lsi_value"]
        pk = payload["pk"]
        key_condition = payload["key_condition"]
        if key_condition == 'begins_with':
            response = table.query(IndexName=f"{index_name}_index",KeyConditionExpression=Key("pk").eq(pk) & Key(index_name).begins_with(lsi_value),)
        elif key_condition == 'between':
            response = table.query(IndexName=f"{index_name}_index",KeyConditionExpression=Key("pk").eq(pk) & Key(index_name).between(lsi_value),) 
        elif key_condition == 'gt':
            response = table.query(IndexName=f"{index_name}_index",KeyConditionExpression=Key("pk").eq(pk) & Key(index_name).gt(lsi_value),) 
        elif key_condition == 'eq':
            response = table.query(IndexName=f"{index_name}_index",KeyConditionExpression=Key("pk").eq(pk) & Key(index_name).eq(lsi_value),) 
        elif key_condition == 'gte':
            response = table.query(IndexName=f"{index_name}_index",KeyConditionExpression=Key("pk").eq(pk) & Key(index_name).gte(lsi_value),) 
        elif key_condition == 'lt':
            response = table.query(IndexName=f"{index_name}_index",KeyConditionExpression=Key("pk").eq(pk) & Key(index_name).lt(lsi_value),) 
        elif key_condition == 'lte':
            response = table.query(IndexName=f"{index_name}_index",KeyConditionExpression=Key("pk").eq(pk) & Key(index_name).lte(lsi_value),) 
        else:
            response = table.query(IndexName=f"{index_name}_index",KeyConditionExpression=Key("pk").eq(pk) & Key(index_name).eq(lsi_value),)
        result_set = response['Items']
        # Deal with Sort Keys [Denver Naidoo - 12 Dec 2021]
        if 'sort_key_date_conversion' in payload:
            sort_key_date_conversion = payload['sort_key_date_conversion']
            if sort_key_date_conversion == True:
                # debugger(sort_key_date_conversion,'get_dynamo_by_pk() => sort_key_date_conversion #3013')
                for item in result_set:
                    item["lsi_date"] = datetime.utcfromtimestamp(int(item["lsi_date"]) // 1000000000).strftime("%d-%b-%Y %H:%M:%S")
        # debugger(sort_key_date_conversion,'get_dynamo_by_pk() => sort_key_date_conversion #3016')
        return result_set
    except Exception as e:
        print(f"get_dynamo_by_pk() => #EXCEPTION: {format(e)}")
        return {"statusCode": 403, "status": "FAILED"}


# -------------------------------------------------------------------------------------------------
# Get the record by pk [Denver Naidoo -11 May 2022]
# -------------------------------------------------------------------------------------------------
def get_dynamo_by_pk(payload):
    try:
        dynamodb = aws.resource("dynamodb")
        table = dynamodb.Table(os.environ.get("DynamoMarketplace"))
        sort_key = {}
        sort_key_name = ""
        sort_key_order = ""
        sort_desc = True
        sort_key_date_conversion = False
        result_set = [{}]
        sorted_result_set = []
        key = {}
        key["pk"] = payload["pk"]
        response = table.query(KeyConditionExpression=Key("pk").eq(key["pk"]))
        result_set = response["Items"]
        # Deal with Sort Keys [Denver Naidoo -11 May 2022]
        if "sort_key" in payload:
            sort_key = payload["sort_key"]
            sort_key_name = sort_key["sort_key_name"]
            sort_key_order = sort_key["sort_key_order"]
            if sort_key_order.upper() == "ASC":
                sort_desc = False
            # sort the results according to the specified order [Denver Naidoo -11 May 2022]
            sorted_result_set = sorted(result_set, key=lambda k: k[sort_key_name], reverse=sort_desc)
            result_set = sorted_result_set
        return result_set
    except Exception as e:
        print(f"get_dynamo_by_pk() => #EXCEPTION: {format(e)}")
        return {"statusCode": 403, "status": "FAILED"}


# -------------------------------------------------------------------------------------------------
# Add item to Dynamo [Denver Naidoo -11 May 2022]
# -------------------------------------------------------------------------------------------------
def add_dynamo(payload):
    dynamodb = aws.resource("dynamodb")
    table = dynamodb.Table(os.environ.get("DynamoMarketplace"))
    try:
        payload = json.loads(json.dumps(payload, default=str))
        payload = json.loads(json.dumps(payload), parse_float=Decimal)
        response = table.put_item(Item=payload)
        return response
    except Exception as e:
        print(f"get_dynamo_by_pk() => #EXCEPTION: {format(e)}")
        return {"statusCode": 403, "status": "FAILED"}


# -------------------------------------------------------------------------------------------------
# DELETE the record by pk_sk [Denver Naidoo -11 May 2022]
# -------------------------------------------------------------------------------------------------
def delete_dynamo_by_pk_sk(payload):
    dynamodb = aws.resource("dynamodb")
    table = dynamodb.Table(os.environ.get("DynamoMarketplace"))
    return_value = {}
    try:
        # Get the current item [Denver Naidoo -11 May 2022]
        original_results = get_dynamo_by_pk_sk(payload)
        if original_results:
            new_pk = original_results["pk"] + "#DELETED"
            original_results["pk"] = new_pk
            # save the deleted item [Denver Naidoo -11 May 2022]
            add_dynamo(original_results)
            # actual delete of the item [Denver Naidoo -11 May 2022]
            response = table.delete_item(Key={"pk": payload["pk"], "sk": payload["sk"]})
            return_value["HTTPStatusCode"] = response["ResponseMetadata"]["HTTPStatusCode"]
        return return_value
    except Exception as e:
        print(f"delete_dynamo_by_pk_sk() => EXCEPTION: {format(e)}")
        return {"statusCode": 403, "status": "FAILED"}


# -------------------------------------------------------------------------------------------------
# Get item by pk and lsi [Denver Naidoo -11 May 2022]
# -------------------------------------------------------------------------------------------------
def get_dynamo_by_pk_lsi(payload):
    dynamodb = aws.resource("dynamodb")
    table = dynamodb.Table(os.environ.get("DynamoMarketplace"))
    try:
        result_set = [{}]
        index_name = payload["lsi_name"]
        lsi_value = payload["lsi_value"]
        pk = payload["pk"]
        response = table.query(
            IndexName=f"{index_name}_index",
            KeyConditionExpression=Key("pk").eq(pk) & Key(index_name).eq(lsi_value),
        )
        result_set = response
        return result_set
    except Exception as e:
        print(f"delete_dynamo_by_pk_sk() => EXCEPTION: {format(e)}")
        return {"statusCode": 403, "status": "FAILED"}


# -------------------------------------------------------------------------------------------------
# Execute SQL on Aurora DB [Denver Naidoo - 11 May 2022]
# -------------------------------------------------------------------------------------------------
def execute_sql(event):
    try:
        user_name = os.environ.get('UserName')
        password = os.environ.get('Password')
        rds_host = os.environ.get('ConnectionString')
        db_name = "marketplace"

        conn = pymysql.connect(host=rds_host, user=user_name, passwd=password, db=db_name, cursorclass=pymysql.cursors.DictCursor)

        # build query
        dbo = event["dbo"]
        event.pop("dbo")

        params = ""
        for item in event:
            params = params + sanitize_field_value(str(event[item])) + ","

        params = params[0:len(params) - 1]

        with conn.cursor() as cursor:
            query = "call pr_" + dbo + "(" + params + ")"
            print('query => ', query)
            cursor.execute(query)
            result = cursor.fetchall()

            return result
    except Exception as err:
        print("error with crud: ", err)
