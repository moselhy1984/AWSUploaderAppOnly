import psutil
import gc

class MemoryManager:
    def __init__(self, max_memory_mb=500):
        self.max_memory_mb = max_memory_mb
        self.cleanup_threshold = 0.8  # 80% of max

    def monitor_and_cleanup(self, app_instance):
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        if memory_mb > (self.max_memory_mb * self.cleanup_threshold):
            # Gradual cleanup
            self.gradual_cleanup(app_instance)
            gc.collect()
            # Check again
            memory_mb = process.memory_info().rss / 1024 / 1024
            if memory_mb > self.max_memory_mb:
                # Aggressive cleanup
                self.aggressive_cleanup(app_instance)
                gc.collect()

    def gradual_cleanup(self, app_instance):
        """Clean up completed/cancelled tasks and unused UI elements."""
        if hasattr(app_instance, 'cleanup_completed_tasks'):
            app_instance.cleanup_completed_tasks()
        if hasattr(app_instance, 'refresh_task_list'):
            app_instance.refresh_task_list()
        if hasattr(app_instance, 'cleanup_hidden_elements'):
            app_instance.cleanup_hidden_elements()

    def aggressive_cleanup(self, app_instance):
        """Forcefully clean up all tasks except running/paused/pending, clear caches, and force GC."""
        if hasattr(app_instance, 'aggressive_cleanup'):
            app_instance.aggressive_cleanup()
        if hasattr(app_instance, 'refresh_task_list'):
            app_instance.refresh_task_list()
        if hasattr(app_instance, 'cleanup_hidden_elements'):
            app_instance.cleanup_hidden_elements()
        gc.collect() 