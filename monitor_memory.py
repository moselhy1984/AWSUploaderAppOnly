#!/usr/bin/env python3
"""Simple memory monitor for AWS Uploader"""
import os
import sys
import time
import datetime

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

def get_memory_usage():
    """Get current process memory usage in MB"""
    if HAS_PSUTIL:
        try:
            # Get current process
            process = psutil.Process(os.getpid())
            # Get memory info in MB
            return process.memory_info().rss / (1024 * 1024)
        except:
            return 0
    return 0

def log(message):
    """Log a message with timestamp"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    sys.stdout.flush()

def monitor_memory(interval=60, log_file=None):
    """
    Monitor memory usage at regular intervals
    
    Args:
        interval (int): Seconds between checks
        log_file (str): Optional log file path
    """
    if not HAS_PSUTIL:
        log("Psutil not installed. Memory monitoring disabled.")
        return

    log(f"Starting memory monitoring every {interval} seconds")
    
    start_time = datetime.datetime.now()
    
    while True:
        # Get memory usage
        mem_usage = get_memory_usage()
        
        # Get run time
        run_time = datetime.datetime.now() - start_time
        hours, remainder = divmod(run_time.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # Log usage
        log(f"Memory usage: {mem_usage:.1f} MB | Runtime: {int(hours)}h {int(minutes)}m {int(seconds)}s")
        
        # Sleep until next check
        time.sleep(interval)

if __name__ == "__main__":
    # Parse arguments
    import argparse
    parser = argparse.ArgumentParser(description="Monitor memory usage of AWS Uploader")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    parser.add_argument("--log-file", type=str, help="Log file path")
    args = parser.parse_args()
    
    monitor_memory(interval=args.interval, log_file=args.log_file)
