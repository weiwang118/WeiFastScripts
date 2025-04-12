# AOSS KNN testing scripts


This script contains some basic testing functionality that you can do on your AOSS vector collection.

All you need to do is have a collection created and then collection endpoint.

## Usage
Copy the python script and install these 3 packages with `pip install`

```
boto3
requests
requests-aws4auth
```

### load creds
You need to do this once, 

```shell
ada credentials update --account=<> --role=Admin --once

export ASSUME_ROLE=arn:aws:iam::<>:role/Admin # provide appropriate role
export STAGE=beta # provide appropriate stage
export REGION=us-east-1 # provide appropriate region
```

### OR 
comment out the `update_ada_credentials` operation inside `main()` provided you have passed in the account and the role in the params

--- 
### Operations 
```shell

ACCOUNT=<aws account that you created the collection in>
ENDPOINT=<Colelction endpoint url>
python3 aoss_testing.py \
    --account $ACCOUNT \
    --endpoint $ENDPOINT \
    --operation create_vector_index \
    --index my-vector-index \
    --dimension 128
```

#### OpenSearch Operations

```json
{
    "operations": [
        "list_indices",
        "create_vector_index",
        "create_text_index", 
        "ingest_vector_doc",
        "bulk_ingest_vectors",
        "search_vector_doc",
        "get_index_settings",
        "delete_documents",
        "get_all_documents", 
        "get_index_health",
        "get_shard_info",
        "add_text_doc",
        "search_text_doc",
        "add_specific_doc",
        "search_specific_doc"
    ]
}

```
### Usage Examples
```bash
# List indices
python3script.py --account <ACCOUNT> --role Admin --endpoint <ENDPOINT> --operation list_indices

# Create vector index
python3 script.py --account <ACCOUNT> --role Admin --endpoint <ENDPOINT> \
    --operation create_vector_index --index my-index --dimension 128

# Bulk ingest vectors
python3 script.py --account <ACCOUNT> --role Admin --endpoint <ENDPOINT> \
    --operation bulk_ingest_vectors --index my-index --num_docs 100 --dimension 128

# Search vectors
python3 script.py --account <ACCOUNT> --role Admin --endpoint <ENDPOINT> \
    --operation search_vector_doc --index my-index
```


