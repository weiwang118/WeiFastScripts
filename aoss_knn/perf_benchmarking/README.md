## to run perf benchmarking against aoss collection 


### Batch ingestion 

Ingest your dataset in batches of 1M each. The procedure `batch_ingestion.json` basically provides a way to ingest data in small batches of 1M for your overall data. 

### Example workload params file

`case2_100M_128d_params.json` is an example workload params file. you can modify it to create the index of right engine type (nmslib / faiss) and also change the dataset location directory. 
Based on the dataset, change the vector dimensions.

`starting_offset` : this is a parameter that helps you start ingesting your data from an offset. By default, starting offset is set to 0. 

Same params file can be used for search workloads too.


---- 

### Benchmarking script

The script `execute-ingest-script.sh` helps automate your batched ingestion workload.

Change the `TOTAL_VECTORS` based on your dataset - 10M, 100M, 1B etc... 

use `--prepare-index` to only create the index for you

use `--ingest` to start the ingestion in batches. 


Parameter `--endpoint` is always required to point it to the right collection endpoint` 

Make sure you have loaded the AWS credentials required to run the benchmarking into the environment variables.



