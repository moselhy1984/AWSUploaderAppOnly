#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import mysql.connector
from datetime import date
import platform
import ssl
import time
from typing import Optional, Dict, Any, List, Union, Tuple
from contextlib import contextmanager

class DatabaseManager:
    """
    Optimized database manager with connection pooling and schema caching
    """
    def __init__(self):
        # Base configuration
        self.rds_config = {
            'host': 'regandb.cvqgwe0s45fi.me-south-1.rds.amazonaws.com',
            'user': 'admin',
            'password': 'Regan4532148',
            'database': 'regandb',
            'port': 3306,
            'charset': 'utf8mb4',
            'collation': 'utf8mb4_unicode_ci',
            'autocommit': False,
            'use_unicode': True,
            'pool_name': 'uploader_pool',
            'pool_size': 5,
            'pool_reset_session': True,
        }
        
        # Windows-specific database configuration
        if platform.system() == 'Windows':
            self.rds_config.update({
                'ssl_disabled': True,  # Disable SSL on Windows to avoid certificate issues
                'auth_plugin': 'mysql_native_password',
                'connection_timeout': 30,
                'allow_local_infile': False,
                'use_pure': True,  # Use pure Python implementation on Windows
            })
        else:
            # macOS/Linux configuration - optimized for RDS compatibility
            self.rds_config.update({
                'ssl_disabled': False,  # Start with SSL enabled for RDS
                'ssl_verify_cert': False,  # Don't verify certificate
                'ssl_verify_identity': False,  # Don't verify identity
                'ssl_ca': None,  # No CA file
                'connection_timeout': 30,  # Increased timeout for SSL handshake
                'use_pure': True,  # Use pure Python implementation for better compatibility
            })
        
        self.connection_pool: Optional[Any] = None
        self.selected_date: Optional[str] = None
        self.system = platform.system()
        
        # Internal pool connection for backwards compatibility
        self._current_connection: Optional[Any] = None
        
        # Schema cache for performance optimization
        self.schema_cache: Dict[str, Any] = {
            'tables_checked': False,
            'columns_checked': False,
            'uploads_has_photographer_columns': None,
            'devices_has_storage_path_column': None,
            'employees_table_exists': None,
            'last_check_time': 0,
            'cache_ttl': 300  # 5 minutes cache
        }
        
        # Connection retry configuration
        self.retry_config = {
            'max_retries': 3,
            'retry_delay': 1.0,
            'backoff_factor': 2.0
        }
        
        # Prepared statements for frequently used queries
        self.prepared_queries = {
            'authenticate_user': """
                SELECT Emp_ID, Emp_FullName, Emp_MacAddress, Emp_Admin, Emp_UserName
                FROM employees 
                WHERE Emp_UserName = %s AND Emp_Password = %s
            """,
            'get_photographers': """
                SELECT e.Emp_ID, e.Emp_FullName, e.Emp_NikName
                FROM employees e
                JOIN jobs j ON e.Emp_JobID = j.Job_ID
                WHERE j.Department_ID = 4
                AND e.Emp_Active_In = 1
                ORDER BY e.Emp_FullName
            """,
            'get_orders_by_date': """
                SELECT 
                    Order_Num_ID as order_id, 
                    Order_Num as order_number,
                    Customer_ID as customer_id, 
                    Order_Date as order_date,
                    OrderType as order_type,
                    Creator_User as creator
                FROM f_order
                WHERE DATE(Order_Date) = %s
                AND Cancel_Order = 0
                ORDER BY Order_TimeStamp DESC
            """,
            'get_device_info': """
                SELECT DeviceID, DeviceName, local_storage_path FROM devices WHERE Mac_Address = %s
            """,
            'update_device_storage': """
                UPDATE devices SET local_storage_path = %s WHERE Mac_Address = %s
            """,
            'get_order_details': """
                SELECT 
                    Order_Num_ID as order_id,
                    Order_Num as order_number,
                    Customer_ID as customer_id, 
                    Order_Date as order_date,
                    OrderType as order_type,
                    Creator_User as creator,
                    GoogleDriveLink as google_drive_link,
                    Booking_Note as booking_note
                FROM f_order
                WHERE Order_Num = %s
            """,
            'find_admin_user': """
                SELECT Emp_ID, Emp_FullName, Emp_MacAddress, Emp_Admin, Emp_UserName
                FROM employees 
                WHERE Emp_Admin = 1 AND Emp_Active_In = 1
                LIMIT 1
            """,
            'find_active_user': """
                SELECT Emp_ID, Emp_FullName, Emp_MacAddress, Emp_Admin, Emp_UserName
                FROM employees 
                WHERE Emp_Active_In = 1
                LIMIT 1
            """
        }
        
        # Dynamic queries that change based on schema
        self.dynamic_queries = {
            'uploads_simple': {
                'today': """
                    SELECT 
                        o.Order_Num_ID as order_id, 
                        o.Order_Num as order_number,
                        o.Customer_ID as customer_id, 
                        o.Order_Date as order_date,
                        o.OrderType as order_type,
                        u.upload_timestamp as upload_time,
                        u.file_count as file_count
                    FROM f_order o
                    JOIN uploads u ON o.Order_Num = u.order_number
                    WHERE DATE(u.upload_timestamp) = %s
                    ORDER BY u.upload_timestamp DESC
                """,
                'filtered': """
                    SELECT 
                        o.Order_Num_ID as order_id, 
                        o.Order_Num as order_number,
                        o.Customer_ID as customer_id, 
                        o.Order_Date as order_date,
                        o.OrderType as order_type,
                        u.upload_timestamp as upload_time,
                        u.file_count as file_count
                    FROM f_order o
                    JOIN uploads u ON o.Order_Num = u.order_number
                    WHERE 1=1
                """,
                'details': """
                    SELECT 
                        upload_id,
                        file_count, 
                        upload_timestamp
                    FROM uploads
                    WHERE order_number = %s
                    ORDER BY upload_timestamp DESC
                """,
                'insert': """
                    INSERT INTO uploads (
                        order_number, 
                        file_count, 
                        upload_timestamp
                    )
                    VALUES (%s, %s, NOW())
                """
            },
            'uploads_with_photographers': {
                'today': """
                    SELECT 
                        o.Order_Num_ID as order_id, 
                        o.Order_Num as order_number,
                        o.Customer_ID as customer_id, 
                        o.Order_Date as order_date,
                        o.OrderType as order_type,
                        u.upload_timestamp as upload_time,
                        u.file_count as file_count,
                        u.main_photographer_id as main_photographer_id,
                        u.assistant_photographer_id as assistant_photographer_id,
                        u.video_photographer_id as video_photographer_id,
                        e1.Emp_FullName as main_photographer_name,
                        e2.Emp_FullName as assistant_photographer_name,
                        e3.Emp_FullName as video_photographer_name
                    FROM f_order o
                    JOIN uploads u ON o.Order_Num = u.order_number
                    LEFT JOIN employees e1 ON u.main_photographer_id = e1.Emp_ID
                    LEFT JOIN employees e2 ON u.assistant_photographer_id = e2.Emp_ID
                    LEFT JOIN employees e3 ON u.video_photographer_id = e3.Emp_ID
                    WHERE DATE(u.upload_timestamp) = %s
                    ORDER BY u.upload_timestamp DESC
                """,
                'filtered': """
                    SELECT 
                        o.Order_Num_ID as order_id, 
                        o.Order_Num as order_number,
                        o.Customer_ID as customer_id, 
                        o.Order_Date as order_date,
                        o.OrderType as order_type,
                        u.upload_timestamp as upload_time,
                        u.file_count as file_count,
                        u.main_photographer_id as main_photographer_id,
                        u.assistant_photographer_id as assistant_photographer_id,
                        u.video_photographer_id as video_photographer_id,
                        e1.Emp_FullName as main_photographer_name,
                        e2.Emp_FullName as assistant_photographer_name,
                        e3.Emp_FullName as video_photographer_name
                    FROM f_order o
                    JOIN uploads u ON o.Order_Num = u.order_number
                    LEFT JOIN employees e1 ON u.main_photographer_id = e1.Emp_ID
                    LEFT JOIN employees e2 ON u.assistant_photographer_id = e2.Emp_ID
                    LEFT JOIN employees e3 ON u.video_photographer_id = e3.Emp_ID
                    WHERE 1=1
                """,
                'details': """
                    SELECT 
                        upload_id,
                        file_count, 
                        upload_timestamp,
                        main_photographer_id,
                        assistant_photographer_id,
                        video_photographer_id,
                        e1.Emp_FullName as main_photographer_name,
                        e2.Emp_FullName as assistant_photographer_name,
                        e3.Emp_FullName as video_photographer_name
                    FROM uploads
                    LEFT JOIN employees e1 ON uploads.main_photographer_id = e1.Emp_ID
                    LEFT JOIN employees e2 ON uploads.assistant_photographer_id = e2.Emp_ID
                    LEFT JOIN employees e3 ON uploads.video_photographer_id = e3.Emp_ID
                    WHERE order_number = %s
                    ORDER BY upload_timestamp DESC
                """,
                'insert': """
                    INSERT INTO uploads (
                        order_number, 
                        file_count, 
                        upload_timestamp, 
                        main_photographer_id,
                        assistant_photographer_id,
                        video_photographer_id
                    )
                    VALUES (%s, %s, NOW(), %s, %s, %s)
                """
            }
        }
        
        print(f"🖥️ Optimized database manager initialized for {self.system}")
    
    def _is_cache_valid(self) -> bool:
        """Check if schema cache is still valid"""
        current_time = time.time()
        return (current_time - self.schema_cache['last_check_time']) < self.schema_cache['cache_ttl']
    
    def _initialize_schema_cache(self) -> bool:
        """Initialize schema cache with database structure information"""
        try:
            if self._is_cache_valid() and self.schema_cache['tables_checked']:
                return True
                
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if uploads table has photographer columns
                cursor.execute("""
                SELECT COUNT(*) as column_exists 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'uploads' 
                AND COLUMN_NAME = 'main_photographer_id'
                """, (self.rds_config['database'],))
                
                result = cursor.fetchone()
                self.schema_cache['uploads_has_photographer_columns'] = bool(result and result[0] > 0)  # type: ignore
                
                # Check if devices table has storage path column
                cursor.execute("""
                SELECT COUNT(*) as column_exists 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'devices' 
                AND COLUMN_NAME = 'local_storage_path'
                """, (self.rds_config['database'],))
                
                result = cursor.fetchone()
                self.schema_cache['devices_has_storage_path_column'] = bool(result and result[0] > 0)  # type: ignore
                
                # Check if employees table exists (should always exist, but just in case)
                cursor.execute("""
                SELECT COUNT(*) as table_exists
                FROM information_schema.tables
                WHERE table_schema = %s
                AND table_name = 'employees'
                """, (self.rds_config['database'],))
                
                result = cursor.fetchone()
                self.schema_cache['employees_table_exists'] = bool(result and result[0] > 0)  # type: ignore
                
                # Update cache status
                self.schema_cache['tables_checked'] = True
                self.schema_cache['columns_checked'] = True
                self.schema_cache['last_check_time'] = time.time()
                
                cursor.close()
                
                print("✅ Schema cache initialized successfully")
                return True
                
        except Exception as e:
            print(f"❌ Error initializing schema cache: {e}")
            return False
    
    @contextmanager
    def get_connection(self):
        """Get database connection with automatic retry and cleanup"""
        connection = None
        max_retries = self.retry_config['max_retries']
        
        for attempt in range(max_retries):
            try:
                if self.connection_pool:
                    connection = self.connection_pool.get_connection()
                else:
                    connection = mysql.connector.connect(**self.rds_config)
                
                yield connection
                break
                
            except mysql.connector.Error as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = self.retry_config['retry_delay'] * (self.retry_config['backoff_factor'] ** attempt)
                print(f"⚠️ Connection attempt {attempt + 1} failed, retrying in {wait_time}s...")
                time.sleep(wait_time)
            finally:
                if connection:
                    connection.close()
    
    def connect(self) -> bool:
        """
        Initialize connection pool with cross-platform error handling
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            print(f"🔌 Initializing connection pool on {self.system}...")
            
            # Windows-specific connection handling
            if self.system == 'Windows':
                try:
                    # First attempt: try with SSL disabled
                    self.connection_pool = mysql.connector.pooling.MySQLConnectionPool(**self.rds_config)
                    print("✅ Connection pool initialized with SSL disabled")
                    
                    # Initialize schema cache
                    if not self._initialize_schema_cache():
                        print("⚠️ Schema cache initialization failed, but continuing...")
                    
                    return True
                except mysql.connector.Error as e:
                    print(f"⚠️ SSL disabled connection failed: {e}")
                    
                    # Second attempt: try with minimal SSL
                    config_with_ssl = self.rds_config.copy()
                    config_with_ssl.update({
                        'ssl_disabled': False,
                        'ssl_verify_cert': False,
                        'ssl_verify_identity': False,
                    })
                    try:
                        self.connection_pool = mysql.connector.pooling.MySQLConnectionPool(**config_with_ssl)
                        print("✅ Connection pool initialized with minimal SSL")
                        
                        # Initialize schema cache
                        if not self._initialize_schema_cache():
                            print("⚠️ Schema cache initialization failed, but continuing...")
                        
                        return True
                    except mysql.connector.Error as e2:
                        print(f"❌ All Windows connection attempts failed: {e2}")
                        return False
            else:
                # Unix-like systems (macOS/Linux) - try multiple connection strategies
                try:
                    # First attempt: try with default SSL settings
                    self.connection_pool = mysql.connector.pooling.MySQLConnectionPool(**self.rds_config)
                    print("✅ Connection pool initialized with default SSL settings")
                    
                    # Initialize schema cache
                    if not self._initialize_schema_cache():
                        print("⚠️ Schema cache initialization failed, but continuing...")
                    
                    return True
                except mysql.connector.Error as e:
                    print(f"⚠️ Default SSL connection failed: {e}")
                    
                    # Second attempt: try with SSL disabled
                    config_no_ssl = self.rds_config.copy()
                    config_no_ssl.update({
                        'ssl_disabled': True,
                        'use_pure': True,  # Use pure Python implementation for better compatibility
                    })
                    # Remove SSL-related keys that conflict with ssl_disabled=True
                    config_no_ssl.pop('ssl_ca', None)
                    config_no_ssl.pop('ssl_verify_cert', None)
                    config_no_ssl.pop('ssl_verify_identity', None)
                    
                    try:
                        self.connection_pool = mysql.connector.pooling.MySQLConnectionPool(**config_no_ssl)
                        print("✅ Connection pool initialized with SSL disabled")
                        
                        # Initialize schema cache
                        if not self._initialize_schema_cache():
                            print("⚠️ Schema cache initialization failed, but continuing...")
                        
                        return True
                    except mysql.connector.Error as e2:
                        print(f"⚠️ SSL disabled connection failed: {e2}")
                        
                        # Third attempt: try with required SSL but no verification
                        config_ssl_required = self.rds_config.copy()
                        config_ssl_required.update({
                            'ssl_disabled': False,
                            'ssl_verify_cert': False,
                            'ssl_verify_identity': False,
                            'ssl_ca': None,
                            'use_pure': True,
                            'connection_timeout': 30  # Increase timeout for SSL handshake
                        })
                        
                        try:
                            self.connection_pool = mysql.connector.pooling.MySQLConnectionPool(**config_ssl_required)
                            print("✅ Connection pool initialized with required SSL (no verification)")
                            
                            # Initialize schema cache
                            if not self._initialize_schema_cache():
                                print("⚠️ Schema cache initialization failed, but continuing...")
                            
                            return True
                        except mysql.connector.Error as e3:
                            print(f"❌ All connection attempts failed on {self.system}: {e3}")
                            return False
                
        except mysql.connector.Error as e:
            print(f"❌ Database connection pool error on {self.system}: {e}")
            if 'SSL' in str(e):
                print("🔧 Hint: SSL connection issue detected. This is common with RDS.")
                print("🔧 The application tried multiple SSL configurations but all failed.")
                print("🔧 Check if RDS allows non-SSL connections or verify SSL certificates.")
            return False
        except Exception as e:
            print(f"❌ Unexpected error creating connection pool: {e}")
            return False
    
    def close(self):
        """
        Close the database connection pool
        """
        if self.connection_pool:
            # Connection pools are automatically managed by mysql.connector
            self.connection_pool = None
            print("✅ Connection pool closed")
    
    def authenticate(self, username: str, password: str) -> Union[Dict[str, Any], bool]:
        """
        Authenticate a user without MAC address verification (optimized)
        
        Args:
            username (str): Username
            password (str): Password
            
        Returns:
            dict or False: User info dictionary if successful, False otherwise
        """
        try:
            # Use cached schema information
            if not self.schema_cache['tables_checked']:
                if not self._initialize_schema_cache():
                    print("❌ Schema cache initialization failed")
                    return False
                    
            if not self.schema_cache['employees_table_exists']:
                print("❌ Employees table does not exist!")
                return False
                
            # Use optimized query system
            print(f"Executing authentication query with username: {username}")
            user = self.execute_optimized_query('authenticate_user', (username, password), 'one')
            
            if user:
                # Add login flag
                user['is_logged_in'] = True  # type: ignore
                user['username'] = user['Emp_UserName']  # type: ignore
                print(f"User authenticated: {user['Emp_FullName']}")  # type: ignore
                return user  # type: ignore
            else:
                print(f"Authentication failed for user: {username}")
                return False
                    
        except mysql.connector.Error as e:
            print(f"Database error in authenticate: {str(e)}")
            return False
    
    def verify_user(self, username: str, password: str, mac_address: str) -> Tuple[bool, Union[str, Dict[str, Any]]]:
        """
        Verify user credentials and MAC address (optimized)
        
        Args:
            username (str): Username
            password (str): Password
            mac_address (str): Device MAC address
            
        Returns:
            tuple: (success, result) where success is a boolean and result is either user info or error message
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                
                query = """
                SELECT Emp_ID, Emp_FullName, Emp_MacAddress, Emp_Admin 
                FROM employees 
                WHERE Emp_UserName = %s AND Emp_Password = %s
                """
                cursor.execute(query, (username, password))
                user = cursor.fetchone()
                cursor.close()
            
            if not user:
                return False, "Invalid username or password"
            
            # Handle MAC address comparison safely
            user_mac = user.get('Emp_MacAddress')  # type: ignore
            if user_mac and str(user_mac).lower() != mac_address.lower():
                if user.get('Emp_Admin') != 1:  # If not admin, check MAC address  # type: ignore
                    return False, "This account is not authorized to use this device"
            
            return True, user  # type: ignore
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def get_photographers(self) -> List[Dict[str, Any]]:
        """
        Get all photographers from employees table (optimized)
        
        Returns:
            list: List of photographer dictionaries
        """
        try:
            # Use optimized query system
            photographers = self.execute_optimized_query('get_photographers', (), 'all')
            return photographers or []  # type: ignore
        except mysql.connector.Error as e:
            print(f"Error fetching photographers: {e}")
            return []
    
    def get_todays_orders(self) -> List[Dict[str, Any]]:
        """
        Get orders for the selected date (optimized)
        
        Returns:
            list: List of order dictionaries
        """
        try:
            # If no date is selected, use today's date
            if self.selected_date is None:
                self.selected_date = date.today().strftime('%Y-%m-%d')
            
            # Use optimized query system
            orders = self.execute_optimized_query('get_orders_by_date', (self.selected_date,), 'all')
            return orders or []  # type: ignore
        except mysql.connector.Error as e:
            print(f"Error fetching orders: {e}")
            return []
    
    def get_uploaded_orders_today(self) -> List[Dict[str, Any]]:
        """
        Get uploaded orders for today (optimized)
        
        Returns:
            list: List of uploaded order dictionaries
        """
        try:
            # Use cached schema information
            if not self.schema_cache['columns_checked']:
                if not self._initialize_schema_cache():
                    print("❌ Schema cache initialization failed")
                    return []
                    
            today = date.today().strftime('%Y-%m-%d')
            
            # Use optimized query system
            orders = self.execute_optimized_query('uploads_today', (today,), 'all')
            return orders or []  # type: ignore
        except mysql.connector.Error as e:
            print(f"Error fetching uploaded orders: {e}")
            return []
    
    def get_filtered_uploads(self, from_date: Optional[str] = None, to_date: Optional[str] = None, order_number: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get uploads filtered by date range and/or order number (optimized)
        
        Args:
            from_date (str, optional): Start date for filtering (format: YYYY-MM-DD)
            to_date (str, optional): End date for filtering (format: YYYY-MM-DD)
            order_number (str, optional): Order number to filter by
            
        Returns:
            list: List of filtered uploads
        """
        try:
            # Use cached schema information
            if not self.schema_cache['columns_checked']:
                if not self._initialize_schema_cache():
                    print("❌ Schema cache initialization failed")
                    return []
                    
            # Get base query
            base_query = self.get_query('uploads_filtered')
            if not base_query:
                print("❌ Could not get filtered uploads query")
                return []
                
            # Add filter conditions and parameters
            params = []
            query = base_query
            
            if from_date:
                query += " AND DATE(u.upload_timestamp) >= %s"
                params.append(from_date)
                
            if to_date:
                query += " AND DATE(u.upload_timestamp) <= %s"
                params.append(to_date)
                
            if order_number:
                query += " AND o.Order_Num LIKE %s"
                params.append(f"%{order_number}%")
                
            # Add order by
            query += " ORDER BY u.upload_timestamp DESC"
            
            # Execute query manually since it's dynamic
            with self.get_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(query, params)
                uploads = cursor.fetchall()
                cursor.close()
            
            return uploads or []  # type: ignore
            
        except mysql.connector.Error as e:
            print(f"Error fetching filtered uploads: {e}")
            return []
    
    def get_order_details(self, order_number: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information for a specific order (optimized)
        
        Args:
            order_number (str): Order number to get details for
            
        Returns:
            dict: Order details including upload information
        """
        try:
            # Use cached schema information
            if not self.schema_cache['columns_checked']:
                if not self._initialize_schema_cache():
                    print("❌ Schema cache initialization failed")
                    return None
                    
            # Use optimized query system
            order_details = self.execute_optimized_query('get_order_details', (order_number,), 'one')
            upload_info = self.execute_optimized_query('uploads_details', (order_number,), 'one')
            
            return {
                'order': order_details,
                'upload': upload_info
            }
        except mysql.connector.Error as e:
            print(f"Error fetching order details: {e}")
            return None
    
    def record_upload(self, order_number: str, file_count: int, main_photographer_id: Optional[int], 
                     assistant_photographer_id: Optional[int], video_photographer_id: Optional[int]) -> bool:
        """
        Record the upload in the database with photographer IDs (optimized)
        
        Args:
            order_number (str): Order number
            file_count (int): Number of files uploaded
            main_photographer_id (int): ID of main photographer
            assistant_photographer_id (int): ID of assistant photographer
            video_photographer_id (int): ID of video photographer
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Use cached schema information
            if not self.schema_cache['columns_checked']:
                if not self._initialize_schema_cache():
                    print("❌ Schema cache initialization failed")
                    return False
                    
            # Convert parameters to appropriate types
            try:
                main_id = int(main_photographer_id) if main_photographer_id is not None else None
                assistant_id = int(assistant_photographer_id) if assistant_photographer_id is not None else None
                video_id = int(video_photographer_id) if video_photographer_id is not None else None
                
                print(f"Converting photographer IDs: {main_photographer_id} -> {main_id}, " 
                    f"{assistant_photographer_id} -> {assistant_id}, {video_photographer_id} -> {video_id}")
            except (ValueError, TypeError) as e:
                print(f"Error converting photographer IDs: {e}")
                main_id = None
                assistant_id = None
                video_id = None
            
            # Use optimized query system
            if self.schema_cache['uploads_has_photographer_columns']:
                result = self.execute_optimized_query('uploads_insert', (order_number, file_count, main_id, assistant_id, video_id), 'none')
            else:
                result = self.execute_optimized_query('uploads_insert', (order_number, file_count), 'none')
            
            # Commit the transaction
            with self.get_connection() as conn:
                conn.commit()
            
            return result is not False
        except mysql.connector.Error as e:
            print(f"Error recording upload: {e}")
            return False
        except Exception as ex:
            print(f"Unexpected error: {ex}")
            import traceback
            traceback.print_exc()
            return False
    
    def auto_authenticate(self) -> Union[Dict[str, Any], bool]:
        """
        Automatically authenticate with admin credentials (optimized)
        This is a special function for AUTO_RESUME mode
        
        Returns:
            dict or False: User info dictionary if successful, False otherwise
        """
        try:
            # Use optimized query system
            admin = self.execute_optimized_query('find_admin_user', (), 'one')
            
            if admin:
                # Add login flag
                admin['is_logged_in'] = True  # type: ignore
                admin['username'] = admin['Emp_UserName']  # type: ignore
                print(f"Auto-authenticated as admin: {admin['Emp_FullName']}")  # type: ignore
                return admin  # type: ignore
            else:
                # Try to find any active user
                user = self.execute_optimized_query('find_active_user', (), 'one')
                
                if user:
                    # Add login flag
                    user['is_logged_in'] = True  # type: ignore
                    user['username'] = user['Emp_UserName']  # type: ignore
                    print(f"Auto-authenticated as user: {user['Emp_FullName']}")  # type: ignore
                    return user  # type: ignore
                else:
                    print("No suitable user found for auto-authentication")
                    return False
                
        except mysql.connector.Error as e:
            print(f"Database error in auto_authenticate: {str(e)}")
            return False
    
    def get_device_info_by_mac(self, mac_address: str) -> Optional[Dict[str, Any]]:
        """
        Get DeviceID and DeviceName from devices table by MAC address (optimized)
        """
        try:
            # Use optimized query system
            result = self.execute_optimized_query('get_device_info', (mac_address,), 'one')
            return result if result else None
        except Exception as e:
            print(f"Error getting device info: {e}")
            return None

    def update_device_storage_path(self, mac_address: str, storage_path: str) -> bool:
        """
        Update local_storage_path for a device by MAC address (optimized)
        """
        try:
            # Use cached schema information
            if not self.schema_cache['columns_checked']:
                if not self._initialize_schema_cache():
                    print("❌ Schema cache initialization failed")
                    return False
                    
            # Use cached column information
            if not self.schema_cache['devices_has_storage_path_column']:
                # Add the column if it doesn't exist
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    alter_query = """
                    ALTER TABLE devices ADD COLUMN local_storage_path VARCHAR(500) NULL
                    """
                    cursor.execute(alter_query)
                    conn.commit()
                    cursor.close()
                    print("Added local_storage_path column to devices table")
                    
                    # Update cache
                    self.schema_cache['devices_has_storage_path_column'] = True
            
            # Use optimized query system
            result = self.execute_optimized_query('update_device_storage', (storage_path, mac_address), 'none')
            
            # Commit the transaction
            with self.get_connection() as conn:
                conn.commit()
                
            return result is not False
        except Exception as e:
            print(f"Error updating device storage path: {e}")
            return False

    def get_device_storage_path(self, mac_address: str) -> Optional[str]:
        """
        Get local_storage_path for a device by MAC address (optimized)
        """
        try:
            device_info = self.get_device_info_by_mac(mac_address)
            if device_info and 'local_storage_path' in device_info:
                return device_info.get('local_storage_path')
            return None
        except Exception as e:
            print(f"Error getting device storage path: {e}")
            return None

    def get_query(self, query_type: str, variant: str = 'default') -> str:
        """
        Get optimized query based on current schema and caching
        
        Args:
            query_type: Type of query (e.g., 'authenticate_user', 'uploads_today')
            variant: Query variant (e.g., 'default', 'simple', 'with_photographers')
            
        Returns:
            str: Optimized SQL query
        """
        # Static prepared queries
        if query_type in self.prepared_queries:
            return self.prepared_queries[query_type]
        
        # Dynamic queries based on schema
        if query_type.startswith('uploads_'):
            schema_key = 'uploads_with_photographers' if self.schema_cache.get('uploads_has_photographer_columns') else 'uploads_simple'
            query_key = query_type.replace('uploads_', '')
            
            if schema_key in self.dynamic_queries and query_key in self.dynamic_queries[schema_key]:
                return self.dynamic_queries[schema_key][query_key]
        
        # Fallback to original query if not found
        return ""
    
    def execute_optimized_query(self, query_type: str, params: tuple = (), fetch_type: str = 'all') -> Any:
        """
        Execute optimized query with automatic retry and caching
        
        Args:
            query_type: Type of query to execute
            params: Query parameters
            fetch_type: 'all', 'one', or 'none'
            
        Returns:
            Query results
        """
        query = self.get_query(query_type)
        if not query:
            raise ValueError(f"Unknown query type: {query_type}")
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(query, params)
                
                if fetch_type == 'all':
                    result = cursor.fetchall()
                elif fetch_type == 'one':
                    result = cursor.fetchone()
                elif fetch_type == 'none':
                    result = cursor.rowcount
                else:
                    result = None
                
                cursor.close()
                return result
                
        except mysql.connector.Error as e:
            print(f"❌ Optimized query error ({query_type}): {e}")
            return None if fetch_type in ['all', 'one'] else False

    @property
    def connection(self) -> Optional[Any]:
        """
        Backward compatibility property that gets a connection from the pool
        """
        if not self.connection_pool:
            return None
        
        try:
            # Get a fresh connection from the pool
            if self._current_connection:
                try:
                    # Check if current connection is still valid
                    self._current_connection.ping(reconnect=False)
                    return self._current_connection
                except:
                    # Connection is dead, get a new one
                    self._current_connection = None
            
            # Get new connection from pool
            self._current_connection = self.connection_pool.get_connection()
            return self._current_connection
        except Exception as e:
            print(f"Error getting connection from pool: {e}")
            return None
    
    @connection.setter
    def connection(self, value: Optional[Any]):
        """
        Setter for backward compatibility (though we don't really use it)
        """
        self._current_connection = value