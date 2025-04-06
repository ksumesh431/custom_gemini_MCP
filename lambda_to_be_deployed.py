import json
import boto3
import gzip
import io
def list_tools():
    return {
        "tools": [
            {
                "name": "get_distribution_info",
                "description": "Fetch CloudFront distribution info and CloudWatch log group by distribution ID or name",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Distribution ID or name"
                        }
                    },
                    "required": ["name"]
                }
            },
            {
                "name": "fetch_logs",
                "description": "Fetch recent CloudFront logs from CloudWatch Logs",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "distribution_id": {
                            "type": "string",
                            "description": "CloudFront distribution ID"
                        },
                        "log_group": {
                            "type": "string",
                            "description": "CloudWatch Log Group name"
                        },
                        "max_events": {
                            "type": "integer",
                            "description": "Maximum number of log events to fetch"
                        }
                    },
                    "required": ["distribution_id", "log_group"]
                }
            },
            {
                "name": "analyze_logs",
                "description": "Analyze logs and suggest remediations",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "logs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of log lines"
                        }
                    },
                    "required": ["logs"]
                }
            }
        ]
    }


def get_distribution_info(name):
    client = boto3.client("cloudfront")
    try:
        # Try to get by ID directly
        response = client.get_distribution(Id=name)
        dist = response["Distribution"]
        dist_id = dist["Id"]
        # Assume log group follows this pattern
        log_group = f"/aws/cloudfront/{dist_id}"
        return {
            "distribution_id": dist_id,
            "log_group": log_group
        }
    except client.exceptions.NoSuchDistribution:

        print(f"No distribution found with ID or name: {name}")
        return {"error": f"No distribution found with ID or name: {name}"}
    except Exception as e:
        print(f"Error fetching distribution info: {e}")
        return {"error": f"Failed to get distribution info: {str(e)}"}



def fetch_logs(distribution_id, log_group, max_events=100):
    logs_client = boto3.client("logs", region_name="us-east-1")

    try:
        response = logs_client.filter_log_events(
            logGroupName=log_group,
            limit=max_events,
        )
        log_events = response.get("events", [])
        logs = [event["message"] for event in log_events]
        if not logs:
            return {
                "logs": [],
                "message": f"No recent log events found in log group {log_group}. Please generate some traffic and try again."
            }
        return {"logs": logs}
    except logs_client.exceptions.ResourceNotFoundException:
        return {
            "logs": [],
            "message": f"Log group {log_group} does not exist."
        }
    except Exception as e:
        return {
            "logs": [],
            "message": f"Error fetching logs: {str(e)}"
        }


def analyze_logs(logs):
    issues = []
    for line in logs:
        if "ERROR" in line or "403" in line or "404" in line:
            issues.append(line)
    remediations = []
    if issues:
        remediations.append("Check permissions and error responses.")
    remediations.append("Consider enabling compression for better performance.")
    return {"issues": issues, "remediations": remediations}

def lambda_handler(event, context):
    try:
        path = event.get("rawPath") or event.get("path")
        method = event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod")
        
        if path.endswith("/list_tools") and method == "GET":
            return {
                "statusCode": 200,
                "body": json.dumps(list_tools()),
                "headers": {"Content-Type": "application/json"}
            }
        elif path.endswith("/call_tool") and method == "POST":
            body = json.loads(event.get("body", "{}"))
            tool_name = body.get("tool_name")
            params = body.get("parameters", {})
            if tool_name == "get_distribution_info":
                result = get_distribution_info(**params)
            elif tool_name == "fetch_logs":
                result = fetch_logs(**params)
            elif tool_name == "analyze_logs":
                result = analyze_logs(**params)
            else:
                result = {"error": "Unknown tool"}
            return {
                "statusCode": 200,
                "body": json.dumps(result),
                "headers": {"Content-Type": "application/json"}
            }
        else:
            return {"statusCode": 404, "body": "Not found"}
    except Exception as e:
        print(f"Lambda error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Internal Server Error", "error": str(e)}),
            "headers": {"Content-Type": "application/json"}
        }