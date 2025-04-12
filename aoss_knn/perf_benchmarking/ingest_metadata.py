import json
from datetime import datetime, timedelta, timezone
import sys
import os

PDT = timezone(timedelta(hours=-7))

params_file = sys.argv[1]
result_file = sys.argv[2]
scenario = sys.argv[3]

start_time = os.environ.get("OSB_START_TIME")
end_time = datetime.now(PDT).strftime('%Y-%m-%d %H:%M:%S')

with open(params_file, 'r') as f:
    params = json.load(f)

with open(result_file, 'r') as f:
    result_text = f.read()

index_name = params.get("target_index_name", "unknown")
dataset = params.get("target_index_bulk_index_data_set_path", "unknown")
index_dimension = params.get("target_index_dimension", "unknown")
index_space_type = params.get("target_index_space_type", "unknown")
mode = params.get("mode", "in_memory")
query_count = params.get("query_count", "unknown")
query_k = params.get("query_k", "unknown")
hnsw_ef_search = params.get("hnsw_ef_search", "unknown")
hnsw_ef_construction = params.get("hnsw_ef_construction", "unknown")

# Build markdown string
header_md = f"""# Benchmark Metadata

- **Scenario**: {scenario}
- **Start Time (PDT)**: {start_time}
- **End Time (PDT)**: {end_time}
- **Index Name**: {index_name}
- **DataSet**: {dataset}
- **Vector Dimension**: {index_dimension}
- **Vector SpaceType**: {index_space_type}
- **Index Mode**: {mode}
- **Query Count**: {query_count}
- **Query K**: {query_k}
- **hnsw_ef_search**: {hnsw_ef_search}
- **hnsw_ef_construction**: {hnsw_ef_construction}

---

# Benchmark Results
"""

# Write combined markdown back to file
with open(result_file, 'w') as f:
    f.write(header_md + "\n" + result_text)

print(f"✅ Combined metadata + result markdown written to: {result_file}")
