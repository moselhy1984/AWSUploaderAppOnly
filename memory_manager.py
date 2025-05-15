#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Memory Management Module for AWS Uploader

This module provides memory optimization functions to help prevent memory leaks
and reduce the application's memory footprint.
"""

import gc
import sys
import os
import psutil
import platform
import logging
import time
from datetime import datetime

class MemoryManager:
    """
    Memory Manager for AWS Uploader application
    Monitors and optimizes memory usage to prevent crashes
    """

    def __init__(self, log_to_console=True, log_to_file=True, 
                 log_file_path="memory_usage.log", threshold_mb=1024):
        """
        Initialize the memory manager
        
        Args:
            log_to_console (bool): Whether to log memory stats to console
            log_to_file (bool): Whether to log memory stats to a file
            log_file_path (str): Path to log file if logging to file
            threshold_mb (int): Memory threshold in MB for gc collection
        """
        self.log_to_console = log_to_console
        self.log_to_file = log_to_file
        self.log_file_path = log_file_path
        self.threshold_mb = threshold_mb
        self.process = psutil.Process(os.getpid())
        self.start_time = datetime.now()
        self.last_collection = time.time()
        self.collection_interval = 60  # Run garbage collection every 60 seconds
        
        # Set up logging
        self.logger = logging.getLogger('memory_manager')
        self.logger.setLevel(logging.INFO)
        
        if log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(logging.Formatter(
                '[%(asctime)s] [MEMORY] %(message)s'))
            self.logger.addHandler(console_handler)
            
        if log_to_file:
            file_handler = logging.FileHandler(log_file_path)
            file_handler.setFormatter(logging.Formatter(
                '[%(asctime)s] [MEMORY] %(message)s'))
            self.logger.addHandler(file_handler)
            
        # Initial logging
        self.logger.info(f"Memory Manager initialized on {platform.system()} {platform.release()}")
        self.logger.info(f"Python {sys.version}")
        self.logger.info(f"Memory threshold set to {threshold_mb} MB")
        
        # Log initial memory status
        self.log_memory_usage()
        
        # Enable garbage collection debugging if low memory
        if self.get_available_memory() < 2048:  # Less than 2GB
            self.logger.info("Low memory detected. Enabling aggressive memory management")
            gc.set_debug(gc.DEBUG_LEAK)
            
    def get_memory_usage(self):
        """Get current process memory usage in MB"""
        try:
            # Different methods depending on platform
            if platform.system() == 'Darwin':  # macOS
                # Use rss for macOS
                memory_info = self.process.memory_info()
                return memory_info.rss / (1024 * 1024)
            else:
                # Use more general method for other platforms
                return self.process.memory_info().rss / (1024 * 1024)
        except Exception as e:
            self.logger.error(f"Error getting memory usage: {e}")
            return 0
    
    def get_available_memory(self):
        """Get available system memory in MB"""
        try:
            return psutil.virtual_memory().available / (1024 * 1024)
        except Exception as e:
            self.logger.error(f"Error getting available memory: {e}")
            return 0
    
    def log_memory_usage(self):
        """Log current memory usage"""
        try:
            process_memory = self.get_memory_usage()
            available_memory = self.get_available_memory()
            runtime = datetime.now() - self.start_time
            hours, remainder = divmod(runtime.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            
            self.logger.info(
                f"Memory usage: {process_memory:.1f} MB | "
                f"Available: {available_memory:.1f} MB | "
                f"Runtime: {int(hours)}h {int(minutes)}m {int(seconds)}s"
            )
            
            if process_memory > self.threshold_mb:
                self.logger.warning(
                    f"Memory usage above threshold ({self.threshold_mb} MB)! "
                    f"Current: {process_memory:.1f} MB"
                )
                self.collect_garbage()
        except Exception as e:
            self.logger.error(f"Error logging memory usage: {e}")
    
    def collect_garbage(self, force=False):
        """Run garbage collection"""
        current_time = time.time()
        # Only run collection if forced or interval has elapsed
        if force or (current_time - self.last_collection >= self.collection_interval):
            try:
                self.logger.info("Running garbage collection...")
                before_memory = self.get_memory_usage()
                
                # Run collection
                collected = gc.collect()
                
                after_memory = self.get_memory_usage()
                memory_diff = before_memory - after_memory
                
                self.logger.info(
                    f"Garbage collection completed: {collected} objects collected. "
                    f"Memory change: {memory_diff:.1f} MB"
                )
                
                self.last_collection = current_time
            except Exception as e:
                self.logger.error(f"Error during garbage collection: {e}")
    
    def clear_large_objects(self, large_obj_threshold_mb=50):
        """Try to identify and clear large objects"""
        try:
            self.logger.info("Scanning for large objects...")
            large_objects = []
            
            # Get all objects
            gc.collect()  # Ensure accurate results
            objects = gc.get_objects()
            
            # Find large objects
            for obj in objects:
                try:
                    obj_size = sys.getsizeof(obj) / (1024 * 1024)
                    if obj_size >= large_obj_threshold_mb:
                        large_objects.append((obj, obj_size))
                except:
                    # Skip objects that can't be sized
                    pass
            
            self.logger.info(f"Found {len(large_objects)} large objects (>{large_obj_threshold_mb} MB)")
            
            # Log details of large objects
            for i, (obj, size) in enumerate(large_objects[:10]):  # Log at most 10
                self.logger.info(f"Large object {i+1}: {type(obj)} - {size:.1f} MB")
                
            return len(large_objects)
        except Exception as e:
            self.logger.error(f"Error scanning for large objects: {e}")
            return 0
    
    def monitor(self, interval=300):
        """
        Start monitoring memory usage at regular intervals
        
        Args:
            interval (int): Monitoring interval in seconds
        """
        self.logger.info(f"Starting memory monitoring at {interval}s intervals")
        
        while True:
            self.log_memory_usage()
            
            # Check if memory is getting high and run more aggressive collection
            if self.get_memory_usage() > (self.threshold_mb * 0.8):
                self.collect_garbage(force=True)
                
                # If still high, try to identify large objects
                if self.get_memory_usage() > (self.threshold_mb * 0.9):
                    self.clear_large_objects()
            
            time.sleep(interval)

# Helper function to add memory management to an application
def setup_memory_management(app=None, threshold_mb=1024):
    """
    Set up memory management for the application
    
    Args:
        app: The application object (optional)
        threshold_mb (int): Memory threshold in MB
        
    Returns:
        MemoryManager: The memory manager instance
    """
    # Create memory manager
    memory_manager = MemoryManager(threshold_mb=threshold_mb)
    
    # Log initial memory state
    memory_manager.log_memory_usage()
    
    # Setup periodic garbage collection
    if app:
        from PyQt5.QtCore import QTimer
        
        # Create timer for memory logging
        memory_timer = QTimer(app)
        memory_timer.timeout.connect(memory_manager.log_memory_usage)
        memory_timer.start(60000)  # Log every minute
        
        # Create timer for garbage collection
        gc_timer = QTimer(app)
        gc_timer.timeout.connect(memory_manager.collect_garbage)
        gc_timer.start(300000)  # Run GC every 5 minutes
    
    return memory_manager

if __name__ == "__main__":
    # When run directly, start memory monitoring
    manager = MemoryManager()
    manager.monitor(interval=60)  # Monitor every 60 seconds 