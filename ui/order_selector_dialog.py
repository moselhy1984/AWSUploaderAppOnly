#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton)

class OrderSelectorDialog(QDialog):
    """
    Dialog for selecting an order from a list
    """
    def __init__(self, orders, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Select Order')
        self.setFixedWidth(300)
        self.layout = QVBoxLayout()
        
        instructions = QLabel("Select an order from today's orders:")
        instructions.setWordWrap(True)
        
        self.order_combo = QComboBox()
        for order in orders:
            # Display order number and customer ID
            self.order_combo.addItem(
                f"{order['order_number']}", 
                order['order_number']  # Use order_number as the data
            )
        
        self.submit_btn = QPushButton('Select')
        self.submit_btn.clicked.connect(self.accept)
        
        self.layout.addWidget(instructions)
        self.layout.addWidget(self.order_combo)
        self.layout.addWidget(self.submit_btn)
        
        self.setLayout(self.layout)
    
    def get_selected_order_id(self):
        """
        Get the selected order ID
        
        Returns:
            str: The selected order ID
        """
        return self.order_combo.currentData()
