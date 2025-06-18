#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import mysql.connector
from mysql.connector import errorcode, pooling
from contextlib import contextmanager
import threading
import time
import logging
from datetime import datetime, timedelta
import json
import queue
from typing import Optional, Dict, Any, List

class DatabasePoolManager:
    """
    محسن لإدارة مجمع اتصالات قاعدة البيانات مع معالجة محسنة للأخطاء
    ومراقبة الأداء وإعادة الاتصال التلقائي
    """
    
    def __init__(self, config: Dict[str, Any], pool_size: int = 5, max_overflow: int = 10):
        """
        تهيئة مدير مجمع قاعدة البيانات
        
        Args:
            config: إعدادات الاتصال بقاعدة البيانات
            pool_size: حجم المجمع الأساسي
            max_overflow: العدد الإضافي للاتصالات المؤقتة
        """
        self.config = config.copy()
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool = None
        self.overflow_connections = 0
        self.connection_count = 0
        self.failed_connections = 0
        self.last_health_check = None
        self.health_status = "unknown"
        
        # إعدادات إضافية لتحسين الأداء
        self.config.update({
            'autocommit': False,
            'use_unicode': True,
            'charset': 'utf8mb4',
            'collation': 'utf8mb4_unicode_ci',
            'connect_timeout': 10,
            'sql_mode': '',
            'raise_on_warnings': True,
            'pool_reset_session': True,
        })
        
        # نظام إعادة المحاولة
        self.retry_config = {
            'max_retries': 3,
            'retry_delay': 1,  # ثانية
            'backoff_factor': 2,
            'max_delay': 30,  # ثانية
        }
        
        # إحصائيات الأداء
        self.stats = {
            'total_connections': 0,
            'active_connections': 0,
            'failed_connections': 0,
            'average_response_time': 0,
            'last_error': None,
            'last_error_time': None,
            'successful_queries': 0,
            'failed_queries': 0
        }
        
        # قفل للحماية من سباق الخيوط
        self.lock = threading.RLock()
        
        # إعداد نظام التسجيل
        self.logger = logging.getLogger(f"DatabasePool_{id(self)}")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        
        # تهيئة المجمع
        self.initialize_pool()
    
    def initialize_pool(self) -> bool:
        """تهيئة مجمع الاتصالات"""
        try:
            with self.lock:
                if self.pool:
                    self._close_existing_pool()
                
                self.logger.info(f"Initializing database pool with size {self.pool_size}")
                
                self.pool = mysql.connector.pooling.MySQLConnectionPool(
                    pool_name=f"uploader_pool_{int(time.time())}",
                    pool_size=self.pool_size,
                    **self.config
                )
                
                # اختبار المجمع
                if self._test_pool():
                    self.health_status = "healthy"
                    self.last_health_check = datetime.now()
                    self.logger.info("Database pool initialized successfully")
                    return True
                else:
                    self.health_status = "unhealthy"
                    self.logger.error("Database pool test failed")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to initialize database pool: {e}")
            self.health_status = "error"
            self.stats['last_error'] = str(e)
            self.stats['last_error_time'] = datetime.now()
            return False
    
    def _close_existing_pool(self):
        """إغلاق المجمع الموجود بأمان"""
        try:
            if self.pool is not None and hasattr(self.pool, '_cnx_queue') and self.pool._cnx_queue is not None:
                # إغلاق جميع الاتصالات في المجمع
                while not self.pool._cnx_queue.empty():
                    try:
                        cnx = self.pool._cnx_queue.get_nowait()
                        if cnx is not None and hasattr(cnx, "is_connected") and cnx.is_connected():
                            cnx.close()
                    except queue.Empty:
                        break
                    except Exception as e:
                        self.logger.warning(f"Error closing connection: {e}")
            
            self.pool = None
            self.logger.info("Existing pool closed successfully")
            
        except Exception as e:
            self.logger.warning(f"Error closing existing pool: {e}")
    
    def _test_pool(self) -> bool:
        """اختبار صحة المجمع"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                cursor.close()
                return result is not None
        except Exception as e:
            self.logger.error(f"Pool test failed: {e}")
            return False
    
    @contextmanager
    def get_connection(self, timeout: int = 30):
        """
        الحصول على اتصال من المجمع مع معالجة محسنة للأخطاء
        
        Args:
            timeout: مهلة الحصول على الاتصال بالثواني
            
        Yields:
            اتصال قاعدة البيانات
        """
        connection = None
        start_time = time.time()
        is_overflow = False
        
        try:
            with self.lock:
                self.stats['total_connections'] += 1
                
            # محاولة الحصول على اتصال من المجمع
            connection = self._get_connection_from_pool(timeout)
            
            if not connection:
                # إنشاء اتصال إضافي إذا أمكن
                if self.overflow_connections < self.max_overflow:
                    connection = self._create_overflow_connection()
                    is_overflow = True
                else:
                    raise mysql.connector.PoolError("Pool exhausted and max overflow reached")
            
            # اختبار الاتصال
            if not self._test_connection(connection):
                if is_overflow:
                    connection.close()
                raise mysql.connector.DatabaseError("Connection test failed")
            
            with self.lock:
                self.stats['active_connections'] += 1
                
            yield connection
            
            # تأكيد المعاملة إذا لم تكن محددة
            if connection.in_transaction:
                connection.commit()
                
        except Exception as e:
            with self.lock:
                self.stats['failed_connections'] += 1
                self.stats['last_error'] = str(e)
                self.stats['last_error_time'] = datetime.now()
            
            # التراجع عن المعاملة في حالة الخطأ
            if connection and connection.is_connected() and connection.in_transaction:
                try:
                    connection.rollback()
                except Exception as rollback_error:
                    self.logger.warning(f"Rollback failed: {rollback_error}")
            
            self.logger.error(f"Database connection error: {e}")
            raise
            
        finally:
            # تنظيف الاتصال
            self._cleanup_connection(connection, is_overflow)
            
            # تحديث إحصائيات الأداء
            with self.lock:
                if self.stats['active_connections'] > 0:
                    self.stats['active_connections'] -= 1
                
                response_time = time.time() - start_time
                if self.stats['average_response_time'] == 0:
                    self.stats['average_response_time'] = response_time
                else:
                    # متوسط متحرك
                    self.stats['average_response_time'] = (
                        self.stats['average_response_time'] * 0.9 + response_time * 0.1
                    )
    
    def _get_connection_from_pool(self, timeout: int) -> Optional[mysql.connector.MySQLConnection]:
        """الحصول على اتصال من المجمع الأساسي"""
        try:
            if not self.pool:
                self.initialize_pool()
            if self.pool:
                conn = self.pool.get_connection()
                # Ensure returned type is MySQLConnection, not PooledMySQLConnection
                if isinstance(conn, mysql.connector.MySQLConnection):
                    return conn
                elif hasattr(conn, 'connection') and isinstance(conn.connection, mysql.connector.MySQLConnection):
                    return conn.connection  # fallback for some pool implementations
                else:
                    return None
                return None
            else:
                raise
        except Exception as e:
            self.logger.error(f"Error getting connection from pool: {e}")
            return None
    
    def _create_overflow_connection(self) -> mysql.connector.MySQLConnection:
        """إنشاء اتصال إضافي خارج المجمع"""
        try:
            with self.lock:
                self.overflow_connections += 1
            self.logger.debug(f"Creating overflow connection ({self.overflow_connections}/{self.max_overflow})")
            connection = mysql.connector.connect(**self.config)
            if isinstance(connection, mysql.connector.MySQLConnection):
                return connection
            else:
                with self.lock:
                    self.overflow_connections = max(0, self.overflow_connections - 1)
                raise TypeError("Overflow connection is not a MySQLConnection instance")
        except Exception as e:
            with self.lock:
                self.overflow_connections = max(0, self.overflow_connections - 1)
            raise
    
    def _test_connection(self, connection: mysql.connector.MySQLConnection) -> bool:
        """اختبار صحة الاتصال"""
        try:
            if not connection.is_connected():
                return False
            # اختبار سريع بـ ping
            connection.ping(reconnect=False, attempts=1, delay=0)
            return True
        except Exception:
            return False
    
    def _cleanup_connection(self, connection: Optional[mysql.connector.MySQLConnection], is_overflow: bool):
        """تنظيف الاتصال بأمان"""
        if not connection:
            return
            
        try:
            if is_overflow:
                # إغلاق الاتصالات الإضافية
                if connection.is_connected():
                    connection.close()
                with self.lock:
                    self.overflow_connections = max(0, self.overflow_connections - 1)
            else:
                # الاتصالات من المجمع سيتم إرجاعها تلقائياً
                pass
                
        except Exception as e:
            self.logger.warning(f"Error cleaning up connection: {e}")
    
    @contextmanager
    def execute_transaction(self, timeout: int = 30):
        """
        تنفيذ معاملة قاعدة بيانات مع ضمان ACID
        
        Args:
            timeout: مهلة الاتصال
            
        Yields:
            اتصال قاعدة البيانات مع معاملة نشطة
        """
        with self.get_connection(timeout) as connection:
            try:
                connection.start_transaction()
                yield connection
                connection.commit()
                
            except Exception as e:
                connection.rollback()
                self.logger.error(f"Transaction rolled back due to error: {e}")
                raise

    def execute_query(
        self,
        query: str,
        params: tuple = (),
        fetch: str = "",
        timeout: int = 30
    ) -> Any:
        """
        تنفيذ استعلام مع إعادة المحاولة التلقائية
        """
        max_retries = self.retry_config['max_retries']
        retry_delay = self.retry_config['retry_delay']
        for attempt in range(max_retries):
            try:
                with self.get_connection(timeout) as connection:
                    cursor = connection.cursor(dictionary=True)
                    start_time = time.time()
                    cursor.execute(query, params)
                    result = None
                    if fetch == 'all':
                        result = cursor.fetchall()
                    elif fetch == 'one':
                        result = cursor.fetchone()
                    elif fetch == 'many':
                        result = cursor.fetchmany()
                    elif query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                        result = cursor.lastrowid if cursor.lastrowid else cursor.rowcount
                    cursor.close()
                    with self.lock:
                        self.stats['successful_queries'] += 1
                    query_time = time.time() - start_time
                    self.logger.debug(f"Query executed successfully in {query_time:.3f}s")
                    return result
            except (mysql.connector.Error, Exception) as e:
                with self.lock:
                    self.stats['failed_queries'] += 1
                if attempt == max_retries - 1:
                    self.logger.error(f"Query failed after {max_retries} attempts: {e}")
                    raise
                else:
                    wait_time = min(
                        retry_delay * (self.retry_config['backoff_factor'] ** attempt),
                        self.retry_config['max_delay']
                    )
                    self.logger.warning(f"Query attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s")
                    time.sleep(wait_time)
    
    def execute_many(self, query: str, param_list: List[tuple], timeout: int = 60) -> int:
        """
        تنفيذ عدة استعلامات في معاملة واحدة
        
        Args:
            query: استعلام SQL
            param_list: قائمة معاملات الاستعلامات
            timeout: مهلة الاتصال
            
        Returns:
            عدد الصفوف المتأثرة
        """
        if param_list is None:
            param_list = []
        with self.execute_transaction(timeout) as connection:
            cursor = connection.cursor()
            cursor.executemany(query, param_list)
            affected_rows = cursor.rowcount
            cursor.close()
            
            self.logger.info(f"Executed batch query affecting {affected_rows} rows")
            return affected_rows
    
    def health_check(self) -> Dict[str, Any]:
        """فحص صحة قاعدة البيانات والمجمع"""
        try:
            start_time = time.time()
            
            # اختبار الاتصال
            with self.get_connection(timeout=5) as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT 1 as test, NOW() as server_time")
                result = cursor.fetchone()
                cursor.close()
            
            response_time = time.time() - start_time
            
            health_info = {
                'status': 'healthy',
                'response_time': response_time,
                'server_time': result[1] if result else None,
                'pool_size': self.pool_size,
                'overflow_connections': self.overflow_connections,
                'stats': self.stats.copy(),
                'last_check': datetime.now().isoformat()
            }
            
            self.health_status = 'healthy'
            self.last_health_check = datetime.now()
            
            return health_info
            
        except Exception as e:
            self.health_status = 'unhealthy'
            return {
                'status': 'unhealthy',
                'error': str(e),
                'last_check': datetime.now().isoformat(),
                'stats': self.stats.copy()
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """الحصول على إحصائيات المجمع"""
        with self.lock:
            stats = self.stats.copy()
            
        stats.update({
            'pool_size': self.pool_size,
            'max_overflow': self.max_overflow,
            'current_overflow': self.overflow_connections,
            'health_status': self.health_status,
            'last_health_check': self.last_health_check.isoformat() if self.last_health_check else None
        })
        
        return stats
    
    def close(self):
        """إغلاق المجمع وجميع الاتصالات"""
        try:
            with self.lock:
                self.logger.info("Closing database pool...")
                
                if self.pool:
                    self._close_existing_pool()
                
                self.health_status = 'closed'
                self.logger.info("Database pool closed successfully")
                
        except Exception as e:
            self.logger.error(f"Error closing database pool: {e}")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class EnhancedDatabaseManager:
    """
    مدير قاعدة البيانات المحسن مع استخدام مجمع الاتصالات
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pool_manager = None
        self.logger = logging.getLogger("EnhancedDatabaseManager")
        self.initialize_pool()
    
    def initialize_pool(self):
        """تهيئة مجمع الاتصالات"""
        try:
            self.pool_manager = DatabasePoolManager(self.config)
            self.logger.info("Enhanced database manager initialized with connection pool")
        except Exception as e:
            self.logger.error(f"Failed to initialize database pool: {e}")
            raise
    
    def connect(self) -> bool:
        """التحقق من الاتصال وإعادة تهيئة المجمع إذا لزم الأمر"""
        if not self.pool_manager:
            raise RuntimeError("Database pool manager not initialized")
        health = self.pool_manager.health_check()
        return health['status'] == 'healthy'
    
    def get_connection(self, timeout: int = 30):
        """الحصول على اتصال من المجمع"""
        if not self.pool_manager:
            raise RuntimeError("Database pool manager not initialized")
        return self.pool_manager.get_connection(timeout)
    
    def execute_query(self, query: str, params: tuple = (), fetch: str = "", timeout: int = 30) -> Any:
        """تنفيذ استعلام باستخدام المجمع"""
        if not self.pool_manager:
            raise RuntimeError("Database pool manager not initialized")
        return self.pool_manager.execute_query(query, params, fetch, timeout)
    
    def execute_transaction(self, timeout: int = 30):
        """بدء معاملة قاعدة بيانات"""
        if not self.pool_manager:
            raise RuntimeError("Database pool manager not initialized")
        return self.pool_manager.execute_transaction(timeout)
    
    def save_task_optimized(self, task_data: Dict[str, Any]) -> Optional[int]:
        """حفظ مهمة باستخدام المجمع المحسن"""
        if not self.pool_manager:
            raise RuntimeError("Database pool manager not initialized")
        try:
            if task_data.get('db_id'):
                query = """
                UPDATE upload_tasks SET
                    order_number = %s, order_date = %s, folder_path = %s,
                    status = %s, progress = %s, updated_at = NOW()
                WHERE task_id = %s
                """
                params = (
                    task_data['order_number'],
                    task_data['order_date'],
                    task_data['folder_path'],
                    task_data['status'],
                    task_data.get('progress', 0),
                    task_data['db_id']
                )
                self.execute_query(query, params)
                return task_data['db_id']
            else:
                query = """
                INSERT INTO upload_tasks
                (order_number, order_date, folder_path, status, progress, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                """
                params = (
                    task_data['order_number'],
                    task_data['order_date'],
                    task_data['folder_path'],
                    task_data['status'],
                    task_data.get('progress', 0)
                )
                task_id = self.execute_query(query, params)
                self.logger.info(f"Created new task with ID: {task_id}")
                return task_id
        except Exception as e:
            self.logger.error(f"Error saving task: {e}")
            raise
    
    def get_tasks_optimized(self, device_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """الحصول على المهام باستخدام المجمع المحسن"""
        if not self.pool_manager:
            raise RuntimeError("Database pool manager not initialized")
        query = """
        SELECT task_id, order_number, status, progress, created_at, updated_at,
               folder_path, order_date, DeviceID
        FROM upload_tasks
        WHERE DeviceID = %s
        ORDER BY created_at DESC
        LIMIT %s
        """
        return self.execute_query(query, (device_id, limit), fetch='all') or []
    
    def health_check(self) -> Dict[str, Any]:
        """فحص صحة قاعدة البيانات"""
        if not self.pool_manager:
            raise RuntimeError("Database pool manager not initialized")
        return self.pool_manager.health_check()
    
    def get_stats(self) -> Dict[str, Any]:
        """الحصول على إحصائيات الأداء"""
        if not self.pool_manager:
            raise RuntimeError("Database pool manager not initialized")
        return self.pool_manager.get_stats()
    
    def close(self):
        """إغلاق مدير قاعدة البيانات"""
        if self.pool_manager:
            self.pool_manager.close()
            self.pool_manager = None 