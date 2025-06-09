import subprocess
import os
import csv
import datetime
import re
import sys
from typing import Dict, Any, Optional, List

def get_mountstats_snapshot() -> str:
    """Get a snapshot of current NFS metrics"""
    result = subprocess.run(
        ["cat", "/proc/self/mountstats"],
        capture_output=True,
        text=True,
        check=True
    )
    # Filter for EFS mounts
    filtered_output = ""
    capture = False
    for line in result.stdout.splitlines():
        if "fs-" in line and "efs" in line and "amazonaws.com" in line:
            capture = True
        if capture:
            filtered_output += line + "\n"
    return filtered_output


def get_ebs_stats() -> List[Dict[str, Any]]:
    """Get I/O statistics for the EBS volume mounted as root (/)"""
    try:
        # Find the device mounted as root (/)
        df_result = subprocess.run(
            ["df", "-h", "/data"],
            capture_output=True,
            text=True,
            check=True
        )

        # Extract the device name
        root_device = None
        for line in df_result.stdout.splitlines()[1:]:  # Skip header
            parts = line.strip().split()
            if len(parts) >= 6 and parts[5] == '/':
                root_device = parts[0].replace('/dev/', '')
                break

        if not root_device:
            print("Could not find root device")
            return []

        print(f"Found root device: {root_device}")

        # Get iostat for the root device
        iostat_result = subprocess.run(
            ["iostat", "-x", root_device, "1", "1"],
            capture_output=True,
            text=True
        )

        # Parse iostat output
        stats = []
        lines = iostat_result.stdout.splitlines()

        # Find the device stats line and headers
        device_line = None
        headers = None

        for i, line in enumerate(lines):
            if "Device" in line and "r/s" in line and "w/s" in line:
                # This is the header line
                headers = re.split(r'\s+', line.strip())
                # The next line should contain our device stats
                if i + 1 < len(lines) and root_device in lines[i + 1]:
                    device_line = lines[i + 1].strip()
                    break

        if headers and device_line:
            # Split the device line into values
            values = re.split(r'\s+', device_line)

            # Create a dictionary with header->value mapping
            if len(values) >= len(headers):
                device_stats = {}
                for j, header in enumerate(headers):
                    if j < len(values):
                        device_stats[header] = values[j]

                # Add mount point information
                device_stats['mount_point'] = '/'

                # Convert numeric values to float
                for key, value in device_stats.items():
                    if key != 'Device' and key != 'mount_point':
                        try:
                            device_stats[key] = float(value)
                        except ValueError:
                            pass  # Keep as string if not convertible

                stats.append(device_stats)
                print(f"Successfully parsed EBS stats for {root_device}")
        else:
            print(f"Could not find headers or device line in iostat output")
            print("Headers found:", headers is not None)
            print("Device line found:", device_line is not None)

        return stats
    except Exception as e:
        print(f"Error getting EBS stats: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_page_faults() -> List[Dict[str, Any]]:
    """Get page fault statistics for OpenSearch processes"""
    try:
        # Get the OpenSearch PID
        opensearch_pid = get_opensearch_pid()

        if not opensearch_pid:
            print("No OpenSearch PID found")
            return []

        # Get the process stats using /proc/{pid}/stat
        result = subprocess.run(
            ["cat", f"/proc/{opensearch_pid}/stat"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"Failed to read process stats: {result.stderr}")
            return []

        stats = result.stdout.split()

        # Fields 10 and 12 are minor and major page faults
        if len(stats) > 11:
            return [{
                'pid': int(opensearch_pid),
                'min_flt': int(stats[9]),  # Minor page faults
                'maj_flt': int(stats[11]),  # Major page faults
                'cmd': 'opensearch'  # Command
            }]
        else:
            print(f"Insufficient data in process stats: {stats}")
            return []

    except Exception as e:
        print(f"Error getting page fault stats: {e}")
        import traceback
        traceback.print_exc()
        return []


def extract_read_stats(stats: str) -> Optional[Dict[str, int]]:
    """Extract read statistics from mountstats output"""
    for line in stats.splitlines():
        if line.strip().startswith('READ:'):
            try:
                parts = line.strip().split()
                return {
                    'ops': int(parts[1]),  # operations requested
                    'ops_done': int(parts[2]),  # operations performed
                    'ops_merged': int(parts[3]),  # operations merged
                    'sectors': int(parts[4]),  # sectors read
                    'bytes': int(parts[5]),  # bytes read
                    'read_time': int(parts[6]),  # time spent reading
                    'queue_time': int(parts[7]),  # time spent queued
                    'total_time': int(parts[8]),  # total time
                    'in_flight': int(parts[9])  # requests in flight
                }
            except (IndexError, ValueError) as e:
                print(f"Warning: Invalid mountstats format: {e}")
                return None
    print("No READ statistics found in input")
    return None


def append_to_csv(file_name, parsed_stats):
    # Create CSV file with parsed_stats data
    if file_name:
        csv_file_path = f"{file_name}.csv"
        file_exists = os.path.isfile(csv_file_path)

        # Add timestamp to the stats
        parsed_stats['timestamp'] = datetime.datetime.now().isoformat()

        with open(csv_file_path, 'a', newline='') as csvfile:
            fieldnames = list(parsed_stats.keys())
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            # Write header only if file doesn't exist
            if not file_exists:
                writer.writeheader()

            writer.writerow(parsed_stats)

        print(f"Stats appended to {csv_file_path}")


def append_ebs_stats_to_csv(file_name, ebs_stats):
    """Append EBS I/O statistics to a CSV file"""
    if not file_name or not ebs_stats:
        return

    timestamp = datetime.datetime.now().isoformat()
    csv_file_path = f"{file_name}_ebs_stats.csv"
    file_exists = os.path.isfile(csv_file_path)

    with open(csv_file_path, 'a', newline='') as csvfile:
        # Add timestamp and device name to each row
        for i, stat in enumerate(ebs_stats):
            stat['timestamp'] = timestamp
            if 'Device' not in stat:
                stat['Device'] = f"device_{i}"

        fieldnames = list(ebs_stats[0].keys()) if ebs_stats else []
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        # Write header only if file doesn't exist
        if not file_exists and fieldnames:
            writer.writeheader()

        # Write all device stats
        for stat in ebs_stats:
            writer.writerow(stat)

    print(f"EBS stats appended to {csv_file_path}")
    # Print some key metrics for verification
    for stat in ebs_stats:
        print(f"  Device: {stat.get('Device', 'unknown')}")
        print(f"    Read ops/s: {stat.get('r/s', 'N/A')}")
        print(f"    Write ops/s: {stat.get('w/s', 'N/A')}")
        print(f"    Read KB/s: {stat.get('rkB/s', 'N/A')}")
        print(f"    Write KB/s: {stat.get('wkB/s', 'N/A')}")
        print(f"    Utilization: {stat.get('%util', 'N/A')}%")


def append_page_faults_to_csv(file_name, page_fault_stats):
    """Append page fault statistics to a CSV file"""
    if not file_name or not page_fault_stats:
        return

    timestamp = datetime.datetime.now().isoformat()
    csv_file_path = f"{file_name}_page_faults.csv"
    file_exists = os.path.isfile(csv_file_path)

    with open(csv_file_path, 'a', newline='') as csvfile:
        # Add timestamp to each row
        for stat in page_fault_stats:
            stat['timestamp'] = timestamp

        fieldnames = list(page_fault_stats[0].keys()) if page_fault_stats else []
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        # Write header only if file doesn't exist
        if not file_exists and fieldnames:
            writer.writeheader()

        # Write all process stats
        for stat in page_fault_stats:
            writer.writerow(stat)

    print(f"Page fault stats appended to {csv_file_path}")


def get_opensearch_pid():
    """Get the PID of the OpenSearch process"""
    try:
        # Get all OpenSearch processes using shell=True to properly handle pipes
        result = subprocess.run(
            "ps -aux | grep opensearch | grep -v grep",
            shell=True,
            capture_output=True,
            text=True
        )

        if result.returncode != 0 or not result.stdout.strip():
            # Try another approach if the first one fails
            result = subprocess.run(
                "ps -ef | grep opensearch | grep -v grep",
                shell=True,
                capture_output=True,
                text=True
            )

        if result.returncode != 0 or not result.stdout.strip():
            print("No OpenSearch process found")
            return None

        # Parse the output to find the actual Java process, not the strace wrapper
        lines = result.stdout.strip().split('\n')
        for line in lines:
            parts = line.split()
            if len(parts) < 2:
                continue

            # Look for the Java process
            if "java" in line and "opensearch" in line and "strace" not in line[:20]:
                opensearch_pid = parts[1]
                print(f"OpenSearch Java PID: {opensearch_pid}")
                return opensearch_pid

        # If we couldn't find the Java process specifically, use the first PID
        if lines:
            parts = lines[0].split()
            if len(parts) >= 2:
                opensearch_pid = parts[1]
                print(f"OpenSearch PID: {opensearch_pid}")
                return opensearch_pid

        print("Could not extract PID from process list")
        return None

    except Exception as e:
        print(f"Error getting OpenSearch PID: {e}")
        import traceback
        traceback.print_exc()
        return None


def drop_cache(file_name):
    # Create directory if it doesn't exist
    os.makedirs("/home/ec2-user/pagecache_test", exist_ok=True)

    # Get NFS stats
    nfs_stats = get_mountstats_snapshot()
    parsed_stats = extract_read_stats(nfs_stats)

    if parsed_stats:
        print("Extracted read stats:")
        print(parsed_stats)
    else:
        print("No NFS read stats detected")

    # Get EBS stats for root volume
    ebs_stats = get_ebs_stats()
    if ebs_stats:
        print(f"Found EBS root volume stats")
    else:
        print("No EBS root volume stats detected")

    # Get page fault stats for OpenSearch processes
    page_fault_stats = get_page_faults()
    if page_fault_stats:
        print(f"Found {len(page_fault_stats)} OpenSearch processes with page fault stats")
    else:
        print("No OpenSearch processes found for page fault tracking")

    # Create CSV files with stats data
    if parsed_stats:
        append_to_csv(file_name, parsed_stats)

    if ebs_stats:
        append_ebs_stats_to_csv(file_name, ebs_stats)

    if page_fault_stats:
        append_page_faults_to_csv(file_name, page_fault_stats)

    free_space = subprocess.run(
        ["free", "-h"],
        capture_output=True,
        text=True,
        check=True
    )

    print(f"Space Free Before Drop {free_space}")
    # Drop OS page caches
    print("Dropping OS page caches...")
    subprocess.run(["sudo", "sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"], check=True)

    # Clear OpenSearch cache
    print("Clearing OpenSearch cache...")
    try:
        curl_result = subprocess.run(
            ["curl", "-XPOST", "http://localhost:9200/_cache/clear"],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"OpenSearch cache clear response: {curl_result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to clear OpenSearch cache: {e}")
        print(f"Error output: {e.stderr}")

    # Check if largefile exists, if not create it
    subprocess.run(
        ["dd", "if=/dev/zero", "of=/home/ec2-user/pagecache_test/largefile", "bs=1M", "count=31000"],
        check=True
    )

    subprocess.run(
        ["cat", "/home/ec2-user/pagecache_test/largefile"],
        stdout=subprocess.DEVNULL,
        check=True
    )

    subprocess.run(
        ["rm", "/home/ec2-user/pagecache_test/largefile"],
        check=True
    )

    # Drop caches again
    print("Dropping OS page caches again...")
    subprocess.run(["sudo", "sync"], check=True)

    subprocess.run(["sudo", "sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"], check=True)
    free_space_after = subprocess.run(
        ["free", "-h"],
        capture_output=True,
        text=True,
        check=True
    )

    print(f"Space Free After Drop {free_space_after}")
    return

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python drop_cache.py <file_name>")
        sys.exit(1)

    file_name = sys.argv[1]
    drop_cache(file_name)
