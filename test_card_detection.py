#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from utils.memory_card_detector import MemoryCardDetector

class MemoryCardTestDialog(QDialog):
    """حوار اختبار كشف كروت الميموري"""
    
    def __init__(self):
        super().__init__()
        self.detector = MemoryCardDetector()
        self.cards = []
        self.setup_ui()
        self.detect_cards()
        
    def setup_ui(self):
        """إعداد واجهة الاختبار"""
        self.setWindowTitle("🔍 Memory Card Detection Test")
        self.setModal(True)
        self.resize(800, 600)
        
        layout = QVBoxLayout()
        
        # شريط العنوان
        header = QLabel("📱 Memory Card Detection System Test")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 18px; font-weight: bold; padding: 20px;")
        layout.addWidget(header)
        
        # أزرار التحكم
        button_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.detect_cards)
        
        self.details_btn = QPushButton("📋 Show Details")
        self.details_btn.clicked.connect(self.show_selected_details)
        self.details_btn.setEnabled(False)
        
        button_layout.addWidget(self.refresh_btn)
        button_layout.addWidget(self.details_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # قائمة الكروت
        self.cards_list = QListWidget()
        self.cards_list.itemSelectionChanged.connect(self.on_selection_changed)
        self.cards_list.itemDoubleClicked.connect(self.show_selected_details)
        layout.addWidget(self.cards_list)
        
        # منطقة المعلومات
        self.info_area = QTextEdit()
        self.info_area.setMaximumHeight(200)
        self.info_area.setReadOnly(True)
        layout.addWidget(self.info_area)
        
        # زر الإغلاق
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
        
    def detect_cards(self):
        """كشف كروت الميموري"""
        self.info_area.append("🔍 Detecting memory cards...")
        QApplication.processEvents()  # تحديث الواجهة
        
        try:
            self.cards = self.detector.detect_all_cards()
            self.update_cards_list()
            
            if self.cards:
                self.info_area.append(f"✅ Found {len(self.cards)} memory card(s)")
            else:
                self.info_area.append("❌ No memory cards detected")
                
        except Exception as e:
            self.info_area.append(f"❌ Error: {str(e)}")
            
    def update_cards_list(self):
        """تحديث قائمة الكروت"""
        self.cards_list.clear()
        
        for i, card in enumerate(self.cards):
            # إنشاء عنصر القائمة
            item_text = f"📱 {card['name']} ({card['card_type']})"
            item_text += f"\n   📏 {self.detector.format_size(card['total_size'])}"
            item_text += f" | 📷 {card['total_camera_files']} files"
            
            # إضافة للقائمة
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, card)
            
            # تلوين حسب نوع الكارت
            if 'Canon' in card['card_type']:
                item.setBackground(QColor(255, 240, 240))  # أحمر فاتح
            elif 'Nikon' in card['card_type']:
                item.setBackground(QColor(255, 255, 240))  # أصفر فاتح
            elif 'Sony' in card['card_type']:
                item.setBackground(QColor(240, 255, 240))  # أخضر فاتح
            else:
                item.setBackground(QColor(245, 245, 245))  # رمادي فاتح
                
            self.cards_list.addItem(item)
            
    def on_selection_changed(self):
        """عند تغيير الاختيار"""
        has_selection = len(self.cards_list.selectedItems()) > 0
        self.details_btn.setEnabled(has_selection)
        
        if has_selection:
            item = self.cards_list.selectedItems()[0]
            card = item.data(Qt.UserRole)
            self.show_card_summary(card)
            
    def show_card_summary(self, card):
        """عرض ملخص الكارت"""
        summary = self.detector.get_card_summary(card)
        
        # إضافة معلومات إضافية
        summary += f"\n\n📍 Path: {card['path']}"
        summary += f"\n🔧 File System: {card['fstype']}"
        summary += f"\n🕒 Detected: {card['detected_at'][:19]}"
        
        # عرض عينات من الملفات
        if card.get('sample_files'):
            summary += f"\n\n📋 Sample Files:"
            for sample in card['sample_files'][:5]:  # أول 5 ملفات
                summary += f"\n  📄 {sample['name']} ({self.detector.format_size(sample['size'])})"
                
        self.info_area.clear()
        self.info_area.append(summary)
        
    def show_selected_details(self):
        """عرض تفاصيل الكارت المحدد"""
        if not self.cards_list.selectedItems():
            return
            
        item = self.cards_list.selectedItems()[0]
        card = item.data(Qt.UserRole)
        
        details_dialog = CardDetailsDialog(card, self.detector, self)
        details_dialog.exec_()

class CardDetailsDialog(QDialog):
    """حوار تفاصيل الكارت"""
    
    def __init__(self, card, detector, parent=None):
        super().__init__(parent)
        self.card = card
        self.detector = detector
        self.setup_ui()
        
    def setup_ui(self):
        """إعداد واجهة التفاصيل"""
        self.setWindowTitle(f"📱 {self.card['name']} - Details")
        self.setModal(True)
        self.resize(600, 500)
        
        layout = QVBoxLayout()
        
        # إنشاء Tabs للمعلومات المختلفة
        tabs = QTabWidget()
        
        # Tab 1: معلومات عامة
        general_tab = QWidget()
        general_layout = QVBoxLayout()
        
        general_info = f"""
📱 Card Name: {self.card['name']}
🏷️ Type: {self.card['card_type']}
📍 Path: {self.card['path']}
🔧 File System: {self.card['fstype']}
💾 Device: {self.card['device']}

📏 Storage Information:
• Total Size: {self.detector.format_size(self.card['total_size'])}
• Used Space: {self.detector.format_size(self.card['used_size'])} ({self.card['usage_percent']}%)
• Free Space: {self.detector.format_size(self.card['free_size'])}

📷 Camera Content:
• Total Files: {self.card['total_camera_files']}
• Total Size: {self.detector.format_size(self.card['total_camera_size'])}
• Folder Structure: {', '.join(self.card.get('folder_structure', []))}
"""
        
        if self.card.get('latest_file_date'):
            general_info += f"\n🕒 Latest File: {self.card['latest_file_date'][:19]}"
        if self.card.get('oldest_file_date'):
            general_info += f"\n🕒 Oldest File: {self.card['oldest_file_date'][:19]}"
            
        general_text = QTextEdit()
        general_text.setPlainText(general_info)
        general_text.setReadOnly(True)
        general_layout.addWidget(general_text)
        general_tab.setLayout(general_layout)
        
        # Tab 2: إحصائيات الملفات
        files_tab = QWidget()
        files_layout = QVBoxLayout()
        
        files_info = "📊 File Type Statistics:\n\n"
        for file_type, stats in self.card.get('file_types', {}).items():
            percentage = (stats['size'] / self.card['total_camera_size']) * 100 if self.card['total_camera_size'] > 0 else 0
            files_info += f"📄 {file_type}:\n"
            files_info += f"   • Count: {stats['count']} files\n"
            files_info += f"   • Size: {self.detector.format_size(stats['size'])} ({percentage:.1f}%)\n\n"
            
        files_text = QTextEdit()
        files_text.setPlainText(files_info)
        files_text.setReadOnly(True)
        files_layout.addWidget(files_text)
        files_tab.setLayout(files_layout)
        
        # Tab 3: عينات من الملفات
        samples_tab = QWidget()
        samples_layout = QVBoxLayout()
        
        if self.card.get('sample_files'):
            samples_table = QTableWidget()
            samples_table.setColumnCount(4)
            samples_table.setHorizontalHeaderLabels(["Name", "Type", "Size", "Date"])
            samples_table.setRowCount(len(self.card['sample_files']))
            
            for row, sample in enumerate(self.card['sample_files']):
                samples_table.setItem(row, 0, QTableWidgetItem(sample['name']))
                samples_table.setItem(row, 1, QTableWidgetItem(sample['type']))
                samples_table.setItem(row, 2, QTableWidgetItem(self.detector.format_size(sample['size'])))
                samples_table.setItem(row, 3, QTableWidgetItem(sample['date'][:19]))
                
            samples_table.resizeColumnsToContents()
            samples_layout.addWidget(samples_table)
        else:
            no_samples = QLabel("No sample files available")
            no_samples.setAlignment(Qt.AlignCenter)
            samples_layout.addWidget(no_samples)
            
        samples_tab.setLayout(samples_layout)
        
        # إضافة التبويبات
        tabs.addTab(general_tab, "📋 General")
        tabs.addTab(files_tab, "📊 File Types")
        tabs.addTab(samples_tab, "📄 Sample Files")
        
        layout.addWidget(tabs)
        
        # أزرار
        button_layout = QHBoxLayout()
        
        open_btn = QPushButton("📁 Open Card")
        open_btn.clicked.connect(self.open_card)
        
        test_access_btn = QPushButton("🔍 Test Access")
        test_access_btn.clicked.connect(self.test_access)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(open_btn)
        button_layout.addWidget(test_access_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
    def open_card(self):
        """فتح الكارت في Finder/Explorer"""
        import subprocess
        import platform
        
        try:
            if platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", self.card['path']])
            elif platform.system() == "Windows":
                subprocess.Popen(["explorer", self.card['path']])
            else:  # Linux
                subprocess.Popen(["xdg-open", self.card['path']])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Cannot open card: {str(e)}")
            
    def test_access(self):
        """اختبار الوصول للكارت"""
        is_accessible, message = self.detector.is_card_accessible(self.card['path'])
        
        if is_accessible:
            QMessageBox.information(self, "Access Test", f"✅ {message}")
        else:
            QMessageBox.warning(self, "Access Test", f"❌ {message}")

def main():
    """الدالة الرئيسية"""
    app = QApplication(sys.argv)
    
    # تطبيق الثيم
    app.setStyle('Fusion')
    
    dialog = MemoryCardTestDialog()
    dialog.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 