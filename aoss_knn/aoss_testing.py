import argparse
import random
import time
import boto3
import os
import requests
from requests_aws4auth import AWS4Auth
import json
import subprocess
from typing import Optional, Dict, Any

def parse_arguments():
    parser = argparse.ArgumentParser(description='OpenSearch operations script')
    parser.add_argument('--account', required=True, help='AWS account number')
    parser.add_argument('--endpoint', required=True, help='OpenSearch endpoint')
    parser.add_argument('--role', default='Admin', help='AWS role name')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--stage', default='beta', help='Environment stage')
    parser.add_argument('--index', help='Index name for operations')
    parser.add_argument('--dimension', type=int, default=2, help='Vector dimension')
    parser.add_argument('--num_docs', type=int, default=5, help='Number of documents to ingest')
    parser.add_argument('--operation', choices=[
        'list_indices',
        'create_vector_index',
        'create_text_index',
        'ingest_vector_doc',
        'bulk_ingest_vectors',
        'search_vector_doc',
        'get_index_settings',
        'delete_documents',
        'get_all_documents',
        'get_index_health',
        'get_shard_info',
        'add_text_doc',
        'search_text_doc',
        'add_specific_doc',
        'search_specific_doc'
    ], required=True, help='Operation to perform')
    return parser.parse_args()

def update_ada_credentials(account: str, role: str) -> bool:
    try:
        command = ['ada', 'credentials', 'update', f'--account={account}', f'--role={role}', '--once']
        subprocess.run(command, check=True)
        print(f"Successfully updated ada credentials for account {account} with role {role}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to update ada credentials: {e}")
        return False
    except FileNotFoundError:
        print("Ada CLI not found. Please install ada first.")
        return False

def get_credentials() -> Optional[Dict[str, str]]:
    session = boto3.Session()
    credentials = session.get_credentials()
    if credentials is None:
        print("No valid credentials found")
        return None
    return {
        'AccessKeyId': credentials.access_key,
        'SecretAccessKey': credentials.secret_key,
        'SessionToken': credentials.token
    }

class OpenSearchClient:
    def __init__(self, endpoint: str, region: str, credentials: Dict[str, str]):
        self.endpoint = endpoint
        self.region = region
        self.auth = AWS4Auth(
            credentials['AccessKeyId'],
            credentials['SecretAccessKey'],
            region,
            'aoss',
            session_token=credentials['SessionToken']
        )
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Host": endpoint.replace("https://", "")
        }

    def make_request(self, method: str, path: str, json_data: Optional[Dict] = None,
                    params: Optional[Dict] = None) -> Optional[requests.Response]:
        url = f"{self.endpoint}/{path}"
        try:
            response = requests.request(
                method,
                url,
                auth=self.auth,
                headers=self.headers,
                json=json_data,
                params=params
            )
            return response
        except Exception as e:
            print(f"Request failed: {e}")
            return None

    def list_indices(self):
        response = self.make_request('GET', '_cat/indices?format=json')
        if response and response.status_code == 200:
            print("\nIndices:")
            print(json.dumps(response.json(), indent=2))
        else:
            print("Failed to list indices")

    def create_vector_index(self, index_name: str, dimension: int = 2, engine: str = "faiss"):
        index_mapping = {
            "settings": {"index": {"knn": True}},
            "mappings": {
                "properties": {
                    "target_field": {
                        "type": "knn_vector",
                        "dimension": dimension,
                        "method": {
                            "name": "hnsw",
                            "space_type": "l2",
                            "engine": engine
                        }
                    }
                }
            }
        }
        response = self.make_request('PUT', index_name, index_mapping)
        if response:
            print(json.dumps(response.json(), indent=2))

    def create_text_index(self, index_name: str):
        index_mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "description": {"type": "text"},
                    "tags": {"type": "keyword"}
                }
            }
        }
        response = self.make_request('PUT', index_name, index_mapping)
        if response:
            print(json.dumps(response.json(), indent=2))

    def ingest_vector_doc(self, index_name: str, dimension: int = 2):
        document = {
            "target_field": [random.randint(-128, 127) for _ in range(dimension)]
        }
        response = self.make_request('POST', f"{index_name}/_doc", document)
        if response:
            print(json.dumps(response.json(), indent=2))

    def bulk_ingest_vectors(self, index_name: str, num_docs: int = 5, dimension: int = 2):
        bulk_data = []
        for _ in range(num_docs):
            bulk_data.append({"index": {"_index": index_name}})
            bulk_data.append({
                "target_field": [random.randint(-128, 127) for _ in range(dimension)]
            })

        bulk_body = "\n".join(json.dumps(data) for data in bulk_data) + "\n"
        headers = self.headers.copy()
        headers["Content-Type"] = "application/x-ndjson"

        url = f"{self.endpoint}/_bulk"
        response = requests.post(url, auth=self.auth, headers=headers, data=bulk_body)
        if response:
            print(json.dumps(response.json(), indent=2))

    def search_vector_doc(self, index_name: str):
        search_query = {
            "query": {
                "knn": {
                    "target_field": {
                        "vector": [10, 20],
                        "k": 10
                    }
                }
            }
        }
        response = self.make_request('POST', f"{index_name}/_search", search_query)
        if response:
            print(json.dumps(response.json(), indent=2))

    def get_index_settings(self, index_name: str):
        response = self.make_request('GET', f"{index_name}/_settings")
        if response:
            print("\nSettings:")
            print(json.dumps(response.json(), indent=2))

        response = self.make_request('GET', f"{index_name}/_mapping")
        if response:
            print("\nMappings:")
            print(json.dumps(response.json(), indent=2))

    def delete_documents(self, index_name: str, query: Optional[Dict] = None):
        delete_query = {
            "query": query if query else {"match_all": {}}
        }
        response = self.make_request('POST', f"{index_name}/_delete_by_query", delete_query)
        if response:
            print(json.dumps(response.json(), indent=2))

    def get_all_documents(self, index_name: str):
        search_query = {
            "size": 100,
            "query": {"match_all": {}},
            "sort": ["_doc"]
        }
        response = self.make_request('POST', f"{index_name}/_search", search_query)
        if response and response.status_code == 200:
            result = response.json()
            total_docs = result['hits']['total']['value']
            hits = result['hits']['hits']
            print(f"\nTotal documents in index '{index_name}': {total_docs}")
            print("\nDocuments:")
            for hit in hits:
                print(f"\nDocument ID: {hit['_id']}")
                print(json.dumps(hit['_source'], indent=2))
                print("---")

    def get_index_health(self, index_name: str):
        params = {
            'v': 'true',
            'h': 'health,status,pri,rep,docs.count,store.size',
            'format': 'json'
        }
        response = self.make_request('GET', f"_cat/indices/{index_name}", params=params)
        if response:
            print(json.dumps(response.json(), indent=2))

    def get_shard_info(self, index_name: str):
        params = {
            'v': 'true',
            'format': 'json'
        }
        response = self.make_request('GET', f"_cat/shards/{index_name}", params=params)
        if response:
            print(json.dumps(response.json(), indent=2))

    def add_text_doc(self, index_name: str):
        document = {
            "title": "OpenSearch Tutorial",
            "description": "This is a guide about OpenSearch and its features",
            "tags": ["search", "tutorial"]
        }
        response = self.make_request('POST', f"{index_name}/_doc", document)
        if response:
            print(json.dumps(response.json(), indent=2))

    def search_text_doc(self, index_name: str):
        search_query = {
            "query": {
                "match": {
                    "description": "OpenSearch guide"
                }
            }
        }
        response = self.make_request('POST', f"{index_name}/_search", search_query)
        if response:
            print(json.dumps(response.json(), indent=2))

    def add_specific_doc(self, index_name: str):
        document = {
            "target_field": [15.5, 25.7],
            "category": "electronics",
            "price": 299.99,
            "in_stock": True
        }
        response = self.make_request('POST', f"{index_name}/_doc", document)
        if response:
            print(json.dumps(response.json(), indent=2))

    def search_specific_doc(self, index_name: str):
        search_query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"category": "electronics"}},
                        {"range": {"price": {"gte": 290, "lte": 300}}},
                        {"term": {"in_stock": True}}
                    ]
                }
            }
        }
        response = self.make_request('POST', f"{index_name}/_search", search_query)
        if response:
            print(json.dumps(response.json(), indent=2))

def main():
    args = parse_arguments()

    # dont need to run this after every run, just need it for the first time/ when creds expire as long as you are
    # testing against same collection
    # if not update_ada_credentials(args.account, args.role):
    #     return

    # Get credentials
    credentials = get_credentials()
    if not credentials:
        return

    # Initialize OpenSearch client
    client = OpenSearchClient(args.endpoint, args.region, credentials)

    # Execute requested operation
    if not args.index and args.operation not in ['list_indices']:
        print("Index name is required for this operation")
        return

    operations = {
        'list_indices': client.list_indices,
        'create_vector_index': lambda: client.create_vector_index(args.index, args.dimension),
        'create_text_index': lambda: client.create_text_index(args.index),
        'ingest_vector_doc': lambda: client.ingest_vector_doc(args.index, args.dimension),
        'bulk_ingest_vectors': lambda: client.bulk_ingest_vectors(args.index, args.num_docs, args.dimension),
        'search_vector_doc': lambda: client.search_vector_doc(args.index),
        'get_index_settings': lambda: client.get_index_settings(args.index),
        'delete_documents': lambda: client.delete_documents(args.index),
        'get_all_documents': lambda: client.get_all_documents(args.index),
        'get_index_health': lambda: client.get_index_health(args.index),
        'get_shard_info': lambda: client.get_shard_info(args.index),
        'add_text_doc': lambda: client.add_text_doc(args.index),
        'search_text_doc': lambda: client.search_text_doc(args.index),
        'add_specific_doc': lambda: client.add_specific_doc(args.index),
        'search_specific_doc': lambda: client.search_specific_doc(args.index)
    }

    operation = operations.get(args.operation)
    if operation:
        operation()
    else:
        print(f"Unknown operation: {args.operation}")

if __name__ == "__main__":
    main()




