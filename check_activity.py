#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import mysql.connector
from datetime import datetime, timedelta

# Database connection info
rds_config = {
    'host': 'regandb.cvqgwe0s45fi.me-south-1.rds.amazonaws.com',
    'user': 'admin',
    'password': 'Regan4532148',
    'database': 'regandb',
    'port': 3306
}

def format_table(headers, rows):
    """Format data as a text table"""
    # Get column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Build separator line
    sep = '+' + '+'.join('-' * (w + 2) for w in col_widths) + '+'
    
    # Build header
    header = '|' + '|'.join(' ' + h.ljust(w) + ' ' for h, w in zip(headers, col_widths)) + '|'
    
    # Build table
    result = [sep, header, sep]
    for row in rows:
        row_str = '|' + '|'.join(' ' + str(cell).ljust(w) + ' ' for cell, w in zip(row, col_widths)) + '|'
        result.append(row_str)
    result.append(sep)
    
    return '\n'.join(result)

try:
    # Connect to the database
    conn = mysql.connector.connect(**rds_config)
    cursor = conn.cursor(dictionary=True)
    
    # Get last 7 days of activity
    days = 7
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    print(f"\n--- Activity Log (Last {days} Days) ---\n")
    
    # Query for task actions with employee information
    query = '''
    SELECT 
        a.timestamp, 
        a.username,
        a.category, 
        a.action, 
        a.details,
        a.emp_id,
        e.Emp_FullName,
        e.Emp_NikName
    FROM activity_log a
    LEFT JOIN employees e ON a.emp_id = e.Emp_ID
    WHERE a.timestamp >= %s
    ORDER BY a.timestamp DESC
    LIMIT 50
    '''
    
    cursor.execute(query, (start_date,))
    activities = cursor.fetchall()
    
    if activities:
        # Format data for display
        rows = []
        for act in activities:
            # Format timestamp
            timestamp = act['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            
            # Use employee name or username
            name = act['Emp_FullName'] or act['username']
            
            # Create row
            row = [
                timestamp,
                name,
                f"{act['category']}/{act['action']}",
                act['details'][:50]  # Truncate details to prevent wide display
            ]
            rows.append(row)
        
        print(format_table(['Date & Time', 'Employee', 'Activity Type', 'Details'], rows))
        
        # Now show task-specific activity
        print('\n--- Task Operations Log ---\n')
        task_query = '''
        SELECT 
            t.task_id,
            t.order_number,
            t.status,
            t.created_by,
            t.created_at,
            t.last_action_by,
            t.last_action_time
        FROM upload_tasks t
        ORDER BY t.last_action_time DESC
        LIMIT 20
        '''
        
        cursor.execute(task_query)
        tasks = cursor.fetchall()
        
        if tasks:
            task_rows = []
            for task in tasks:
                # Format timestamps
                created_at = task['created_at'].strftime('%Y-%m-%d %H:%M:%S') if task['created_at'] else 'N/A'
                last_action = task['last_action_time'].strftime('%Y-%m-%d %H:%M:%S') if task['last_action_time'] else 'N/A'
                
                # Translate status
                status_map = {
                    'pending': 'Pending',
                    'running': 'Running',
                    'paused': 'Paused',
                    'completed': 'Completed',
                    'failed': 'Failed',
                    'cancelled': 'Cancelled'
                }
                status = status_map.get(task['status'], task['status'])
                
                task_row = [
                    task['task_id'],
                    task['order_number'],
                    status,
                    task['created_by'] or 'Unknown',
                    created_at[:10],  # Just show date
                    task['last_action_by'] or 'Unknown',
                    last_action[:10]  # Just show date
                ]
                task_rows.append(task_row)
            
            print(format_table(['Task ID', 'Order Number', 'Status', 'Created By', 'Creation Date', 'Last Action By', 'Last Action Date'], task_rows))
        else:
            print('No tasks found in database.')
    else:
        print('No activity records found for the selected period.')
        
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f'Error: {str(e)}') 