#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import mysql.connector
from datetime import date

class DatabaseManager:
    """
    Manages database connections and operations
    """
    def __init__(self):
        self.rds_config = {
            'host': 'regandb.cvqgwe0s45fi.me-south-1.rds.amazonaws.com',
            'user': 'admin',
            'password': 'Regan4532148',
            'database': 'regandb',
            'port': 3306
        }
        self.connection = None
        self.selected_date = None  # Default to today's date
    
    def connect(self):
        """
        Connect to the database
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.connection = mysql.connector.connect(**self.rds_config)
            return True
        except mysql.connector.Error as e:
            print(f"Error connecting to database: {e}")
            return False
    
    def close(self):
        """
        Close the database connection
        """
        if self.connection:
            self.connection.close()
    
    def verify_user(self, username, password, mac_address):
        """
        Verify user credentials and MAC address
        
        Args:
            username (str): Username
            password (str): Password
            mac_address (str): Device MAC address
            
        Returns:
            tuple: (success, result) where success is a boolean and result is either user info or error message
        """
        try:
            if not self.connection or not self.connection.is_connected():
                self.connect()
                
            cursor = self.connection.cursor(dictionary=True)
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
            
            if user['Emp_MacAddress'] and user['Emp_MacAddress'].lower() != mac_address.lower():
                if user['Emp_Admin'] != 1:  # If not admin, check MAC address
                    return False, "This account is not authorized to use this device"
            
            return True, user
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def get_photographers(self):
        """
        Get all photographers from employees table
        
        Returns:
            list: List of photographer dictionaries
        """
        try:
            if not self.connection or not self.connection.is_connected():
                self.connect()
                
            cursor = self.connection.cursor(dictionary=True)
            query = """
            SELECT e.Emp_ID, e.Emp_FullName, e.Emp_NikName
            FROM employees e
            JOIN jobs j ON e.Emp_JobID = j.Job_ID
            WHERE j.Department_ID = 4
            AND e.Emp_Active_In = 1
            ORDER BY e.Emp_FullName
            """
            cursor.execute(query)
            photographers = cursor.fetchall()
            cursor.close()
            
            return photographers
        except mysql.connector.Error as e:
            print(f"Error fetching photographers: {e}")
            return []
    
    def get_todays_orders(self):
        """
        Get orders for the selected date
        
        Returns:
            list: List of order dictionaries
        """
        try:
            if not self.connection or not self.connection.is_connected():
                self.connect()
                
            cursor = self.connection.cursor(dictionary=True)
            
            # If no date is selected, use today's date
            if self.selected_date is None:
                self.selected_date = date.today().strftime('%Y-%m-%d')
            
            # Get orders based on the selected date
            query = """
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
            """
            cursor.execute(query, (self.selected_date,))
            orders = cursor.fetchall()
            cursor.close()
            
            return orders
        except mysql.connector.Error as e:
            print(f"Error fetching orders: {e}")
            return []
    
    def get_uploaded_orders_today(self):
        """
        Get uploaded orders for today
        
        Returns:
            list: List of uploaded order dictionaries
        """
        try:
            if not self.connection or not self.connection.is_connected():
                self.connect()
                
            cursor = self.connection.cursor(dictionary=True)
            today = date.today().strftime('%Y-%m-%d')
            
            # Check if the uploads table has the photographer columns
            check_query = """
            SELECT COUNT(*) as column_exists 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'uploads' 
            AND COLUMN_NAME = 'main_photographer_id'
            """
            cursor.execute(check_query, (self.rds_config['database'],))
            result = cursor.fetchone()
            
            # If the column doesn't exist, use a simplified query
            if result['column_exists'] == 0:
                query = """
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
                """
                cursor.execute(query, (today,))
            else:
                # Full query with photographer information
                query = """
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
                """
                cursor.execute(query, (today,))
            
            orders = cursor.fetchall()
            cursor.close()
            
            return orders
        except mysql.connector.Error as e:
            print(f"Error fetching uploaded orders: {e}")
            return []
    
    def get_order_details(self, order_number):
        """
        Get detailed information for a specific order
        
        Args:
            order_number (str): Order number to get details for
            
        Returns:
            dict: Order details including upload information
        """
        try:
            if not self.connection or not self.connection.is_connected():
                self.connect()
                
            cursor = self.connection.cursor(dictionary=True)
            
            # Get order basic details
            order_query = """
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
            """
            cursor.execute(order_query, (order_number,))
            order_details = cursor.fetchone()
            
            # Check if the uploads table has the photographer columns
            check_query = """
            SELECT COUNT(*) as column_exists 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'uploads' 
            AND COLUMN_NAME = 'main_photographer_id'
            """
            cursor.execute(check_query, (self.rds_config['database'],))
            result = cursor.fetchone()
            
            # Get upload information, adapt query based on schema
            if result['column_exists'] == 0:
                upload_query = """
                SELECT 
                    upload_id,
                    file_count, 
                    upload_timestamp
                FROM uploads
                WHERE order_number = %s
                ORDER BY upload_timestamp DESC
                """
                cursor.execute(upload_query, (order_number,))
            else:
                upload_query = """
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
                """
                cursor.execute(upload_query, (order_number,))
            
            upload_info = cursor.fetchone()
            
            cursor.close()
            
            return {
                'order': order_details,
                'upload': upload_info
            }
        except mysql.connector.Error as e:
            print(f"Error fetching order details: {e}")
            return None
    
    def record_upload(self, order_number, file_count, main_photographer_id, assistant_photographer_id, video_photographer_id):
        """
        Record the upload in the database with photographer IDs
        
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
            if not self.connection or not self.connection.is_connected():
                self.connect()
                
            cursor = self.connection.cursor()
            
            # Check if the uploads table has the photographer columns
            check_query = """
            SELECT COUNT(*) as column_exists 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = %s 
            AND TABLE_NAME = 'uploads' 
            AND COLUMN_NAME = 'main_photographer_id'
            """
            cursor.execute(check_query, (self.rds_config['database'],))
            result = cursor.fetchone()
            
            # Handle the result correctly - fetchone() returns a tuple with dictionary parameter names
            # We can safely access the first element as it's the COUNT(*) result
            column_exists = result[0] if result else 0
            
            # Convert parameters to appropriate types
            try:
                # Convert to integers if not None
                main_id = int(main_photographer_id) if main_photographer_id is not None else None
                assistant_id = int(assistant_photographer_id) if assistant_photographer_id is not None else None
                video_id = int(video_photographer_id) if video_photographer_id is not None else None
                
                # Debug output
                print(f"Converting photographer IDs: {main_photographer_id} -> {main_id}, " 
                    f"{assistant_photographer_id} -> {assistant_id}, {video_photographer_id} -> {video_id}")
            except (ValueError, TypeError) as e:
                print(f"Error converting photographer IDs: {e}")
                main_id = None
                assistant_id = None
                video_id = None
            
            # If the columns don't exist, use a simplified query
            if column_exists == 0:
                upload_query = """
                INSERT INTO uploads (
                    order_number, 
                    file_count, 
                    upload_timestamp
                )
                VALUES (%s, %s, NOW())
                """
                cursor.execute(upload_query, (order_number, file_count))
            else:
                # Full query with photographer info
                upload_query = """
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
                
                # Execute the query with proper parameters
                print(f"Executing query with params: {order_number}, {file_count}, {main_id}, {assistant_id}, {video_id}")
                cursor.execute(upload_query, (
                    order_number, 
                    file_count, 
                    main_id, 
                    assistant_id, 
                    video_id
                ))
            
            self.connection.commit()
            cursor.close()
            return True
        except mysql.connector.Error as e:
            print(f"Error recording upload: {e}")
            return False
        except Exception as ex:
            print(f"Unexpected error: {ex}")
            import traceback
            traceback.print_exc()
            return False
