#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import mysql.connector
import sys
from datetime import datetime, timedelta
import argparse

def format_table(headers, rows, max_widths=None):
    """Format data as a text table with optional column width limits"""
    # Get column widths or use provided max widths
    if max_widths is None:
        max_widths = [100] * len(headers)  # Default max width
        
    col_widths = [min(len(h), max_widths[i]) for i, h in enumerate(headers)]
    for row in rows:
        for i, cell in enumerate(row):
            cell_str = str(cell)
            if len(cell_str) > max_widths[i]:
                # Truncate and add ellipsis
                cell_str = cell_str[:max_widths[i]-3] + "..."
            col_widths[i] = max(col_widths[i], min(len(cell_str), max_widths[i]))
    
    # Build separator line
    sep = '+' + '+'.join('-' * (w + 2) for w in col_widths) + '+'
    
    # Build header
    header = '|' + '|'.join(' ' + h.ljust(w) + ' ' for h, w in zip(headers, col_widths)) + '|'
    
    # Build table
    result = [sep, header, sep]
    for row in rows:
        row_str_parts = []
        for i, cell in enumerate(row):
            cell_str = str(cell)
            if len(cell_str) > max_widths[i]:
                cell_str = cell_str[:max_widths[i]-3] + "..."
            row_str_parts.append(' ' + cell_str.ljust(col_widths[i]) + ' ')
        row_str = '|' + '|'.join(row_str_parts) + '|'
        result.append(row_str)
    result.append(sep)
    
    return '\n'.join(result)

def get_employee_activity(conn, employee_name=None, days=7, action_type=None, order_number=None):
    """Get activity log filtered by employee, days, action type, and order number"""
    cursor = conn.cursor(dictionary=True)
    
    # Build WHERE clause and params
    where_clauses = ["a.timestamp >= %s"]
    params = [(datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')]
    
    if employee_name:
        where_clauses.append("(a.username LIKE %s OR e.Emp_FullName LIKE %s)")
        params.extend([f"%{employee_name}%", f"%{employee_name}%"])
    
    if action_type:
        where_clauses.append("a.category = %s")
        params.append(action_type)
    
    if order_number:
        where_clauses.append("a.details LIKE %s")
        params.append(f"%order {order_number}%")
    
    # Build the query
    query = f'''
    SELECT 
        a.id,
        a.timestamp, 
        a.username,
        a.category, 
        a.action, 
        a.details,
        a.ip_address,
        a.device_id,
        a.emp_id,
        e.Emp_FullName,
        e.Emp_NikName
    FROM activity_log a
    LEFT JOIN employees e ON a.emp_id = e.Emp_ID
    WHERE {' AND '.join(where_clauses)}
    ORDER BY a.timestamp DESC
    LIMIT 100
    '''
    
    cursor.execute(query, params)
    activities = cursor.fetchall()
    cursor.close()
    
    return activities

def get_task_operations(conn, employee_name=None, days=None, status=None, order_number=None):
    """Get task operations log filtered by employee, days, status, and order number"""
    cursor = conn.cursor(dictionary=True)
    
    # Build WHERE clause and params
    where_clauses = []
    params = []
    
    if days:
        where_clauses.append("t.last_action_time >= %s")
        params.append((datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d'))
    
    if employee_name:
        where_clauses.append("(t.created_by LIKE %s OR t.last_action_by LIKE %s)")
        params.extend([f"%{employee_name}%", f"%{employee_name}%"])
    
    if status:
        where_clauses.append("t.status = %s")
        params.append(status)
    
    if order_number:
        where_clauses.append("t.order_number LIKE %s")
        params.append(f"%{order_number}%")
    
    # Build the query
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    
    query = f'''
    SELECT 
        t.task_id,
        t.order_number,
        t.status,
        t.progress,
        t.created_by,
        t.created_at,
        t.last_action_by,
        t.last_action_time,
        t.created_by_emp_id,
        t.last_action_by_emp_id,
        e1.Emp_FullName as creator_name,
        e2.Emp_FullName as last_actor_name
    FROM upload_tasks t
    LEFT JOIN employees e1 ON t.created_by_emp_id = e1.Emp_ID
    LEFT JOIN employees e2 ON t.last_action_by_emp_id = e2.Emp_ID
    {where_sql}
    ORDER BY t.last_action_time DESC
    LIMIT 50
    '''
    
    cursor.execute(query, params)
    tasks = cursor.fetchall()
    cursor.close()
    
    return tasks

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Monitor employee actions in AWS Uploader')
    parser.add_argument('-e', '--employee', help='Filter by employee name')
    parser.add_argument('-d', '--days', type=int, default=7, help='Number of days to look back')
    parser.add_argument('-a', '--action', help='Filter by action type (auth, task, upload, etc.)')
    parser.add_argument('-o', '--order', help='Filter by order number')
    parser.add_argument('-s', '--status', help='Filter tasks by status (pending, running, completed, etc.)')
    parser.add_argument('-t', '--tasks-only', action='store_true', help='Show only task operations')
    parser.add_argument('-l', '--logs-only', action='store_true', help='Show only activity logs')
    
    args = parser.parse_args()
    
    # Database connection info
    rds_config = {
        'host': 'regandb.cvqgwe0s45fi.me-south-1.rds.amazonaws.com',
        'user': 'admin',
        'password': 'Regan4532148',
        'database': 'regandb',
        'port': 3306
    }
    
    try:
        # Connect to the database
        conn = mysql.connector.connect(**rds_config)
        
        # Print header with filter info
        print("\n===== AWS Uploader Employee Activity Monitor =====")
        filters = []
        if args.employee:
            filters.append(f"Employee: {args.employee}")
        if args.days:
            filters.append(f"Last {args.days} days")
        if args.action:
            filters.append(f"Action type: {args.action}")
        if args.order:
            filters.append(f"Order: {args.order}")
        if args.status:
            filters.append(f"Status: {args.status}")
            
        if filters:
            print("Filters:", " | ".join(filters))
        print()
        
        # Get and display activity logs
        if not args.tasks_only:
            activities = get_employee_activity(
                conn, 
                employee_name=args.employee,
                days=args.days, 
                action_type=args.action,
                order_number=args.order
            )
            
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
                        act['details'],
                        act['ip_address']
                    ]
                    rows.append(row)
                
                print(f"--- Activity Log ---")
                print(format_table(
                    ['Time', 'Employee', 'Action', 'Details', 'IP Address'], 
                    rows,
                    max_widths=[19, 20, 15, 50, 15]
                ))
                print(f"Total activities: {len(activities)}")
            else:
                print("No activity records found for the selected filters.")
        
        # Now show task-specific activity
        if not args.logs_only:
            print('\n--- Task Operations Log ---\n')
            tasks = get_task_operations(
                conn,
                employee_name=args.employee,
                days=args.days,
                status=args.status,
                order_number=args.order
            )
            
            if tasks:
                task_rows = []
                for task in tasks:
                    # Format timestamps
                    created_at = task['created_at'].strftime('%Y-%m-%d %H:%M:%S') if task['created_at'] else 'N/A'
                    last_action = task['last_action_time'].strftime('%Y-%m-%d %H:%M:%S') if task['last_action_time'] else 'N/A'
                    
                    # Use resolved names if available
                    created_by = task['creator_name'] or task['created_by'] or 'Unknown'
                    last_action_by = task['last_actor_name'] or task['last_action_by'] or 'Unknown'
                    
                    # Format progress
                    progress = f"{task['progress']:.1f}%" if task['progress'] is not None else 'N/A'

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
                        progress,
                        created_by,
                        created_at,
                        last_action_by,
                        last_action
                    ]
                    task_rows.append(task_row)
                
                print(format_table(
                    ['ID', 'Order', 'Status', 'Progress', 'Created By', 'Created At', 'Last Action By', 'Last Action Time'], 
                    task_rows,
                    max_widths=[5, 10, 10, 10, 20, 19, 20, 19]
                ))
                print(f"Total tasks: {len(tasks)}")
            else:
                print('No tasks found for the selected filters.')
            
        conn.close()
        
    except Exception as e:
        print(f'Error: {str(e)}', file=sys.stderr)
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main()) 