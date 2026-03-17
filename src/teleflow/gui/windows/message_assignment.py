from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, 
    QPushButton, QLabel, QMessageBox, QWidget, QLineEdit
)
from PyQt6.QtCore import Qt
from typing import List, Dict, Any
import qasync
from teleflow.core.message_manager import MessageManager
from teleflow.core.chat_manager import ChatManager
from teleflow.gui.styles import TG_BASE_COLORS

class MessageAssignmentDialog(QDialog):
    """Dialog to select which chats a specific message template should be sent to."""
    
    def __init__(self, account_phone: str, msg_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.account_phone = account_phone
        self.msg_id = msg_id
        self.msg_mgr = MessageManager()
        self.chat_mgr = ChatManager()
        self.all_chats: List[Dict[str, Any]] = []
        
        self.setWindowTitle("Назначение чатов")
        self.resize(450, 600)
        self._setup_ui()
        
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        c = TG_BASE_COLORS
        
        lbl_info = QLabel("Выберите чаты для рассылки:")
        lbl_info.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {c['text_main']};")
        layout.addWidget(lbl_info)
        
        # Search Box
        self.search_inp = QLineEdit()
        self.search_inp.setPlaceholderText("🔍 Поиск чатов...")
        self.search_inp.setStyleSheet(f"""
            QLineEdit {{
                border: 1.5px solid {c['border']};
                border-radius: 8px;
                padding: 8px 12px;
                background: {c['bg_sidebar']};
                color: {c['text_main']};
            }}
            QLineEdit:focus {{ border-color: {c['accent']}; }}
        """)
        self.search_inp.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_inp)
        
        self.list_chats = QListWidget()
        self.list_chats.setStyleSheet(f"""
            QListWidget {{
                border: 1.5px solid {c['border']};
                border-radius: 8px;
                background: {c['bg_main']};
                outline: none;
            }}
            QListWidget::item {{
                padding: 12px 14px;
                border-bottom: 1px solid {c['border']};
                color: {c['text_main']};
            }}
            QListWidget::item:hover {{ background: {c['bg_sidebar']}; }}
        """)
        layout.addWidget(self.list_chats)
        
        # Action Buttons
        btn_ly = QHBoxLayout()
        btn_ly.setSpacing(8)
        
        btn_sel_all = QPushButton("Выбрать все")
        btn_sel_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sel_all.setStyleSheet(f"color: {c['accent']}; border: none; font-weight: 600;")
        btn_sel_all.clicked.connect(self._select_all)
        
        btn_cancel = QPushButton("Отмена")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setFixedSize(90, 36)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1.5px solid {c['border']};
                border-radius: 8px;
                color: {c['text_muted']};
            }}
            QPushButton:hover {{ background: {c['bg_sidebar']}; }}
        """)
        btn_cancel.clicked.connect(self.reject)
        
        self.btn_save = QPushButton("Сохранить")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setFixedSize(110, 36)
        self.btn_save.setStyleSheet(f"""
            QPushButton {{
                background: {c['accent']};
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {c['accent_hover']}; }}
        """)
        self.btn_save.clicked.connect(self._on_save)
        
        btn_ly.addWidget(btn_sel_all)
        btn_ly.addStretch()
        btn_ly.addWidget(btn_cancel)
        btn_ly.addWidget(self.btn_save)
        layout.addLayout(btn_ly)

    def _on_search_changed(self, text: str) -> None:
        text = text.lower()
        for i in range(self.list_chats.count()):
            item = self.list_chats.item(i)
            if item:
                # We store the chat title in the text, but let's be robust
                item.setHidden(text not in item.text().lower())
        
    def _select_all(self) -> None:
        for i in range(self.list_chats.count()):
            item = self.list_chats.item(i)
            if item:
                item.setCheckState(Qt.CheckState.Checked)

    async def load_data(self) -> None:
        """Fetch all local chats and currently assigned ones."""
        self.all_chats = await self.chat_mgr.get_chats_for_account(self.account_phone)
        assigned_links = await self.msg_mgr.get_assigned_chats_for_message(self.msg_id)
        assigned_ids = {link["db_chat_id"] for link in assigned_links if link["is_active"]}
        
        self.list_chats.clear()
        for chat in self.all_chats:
            c_type = chat.get('type', 'User')
            icon_map = {"User": "👤", "Group": "👥", "Channel": "📢"}
            icon = icon_map.get(c_type, "💬")
            
            item = QListWidgetItem(f"{icon} {chat['title']}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            
            # db actual ID is 'id' vs telegram 'chat_id'
            db_id = chat["id"] 
            item.setData(Qt.ItemDataRole.UserRole, db_id)
            
            if db_id in assigned_ids:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
                
            self.list_chats.addItem(item)

    @qasync.asyncSlot()
    async def _on_save(self) -> None:
        selected_db_ids = []
        for i in range(self.list_chats.count()):
            item = self.list_chats.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                db_id = item.data(Qt.ItemDataRole.UserRole)
                selected_db_ids.append(db_id)
                
        self.btn_save.setEnabled(False)
        self.btn_save.setText("Saving...")
        
        success = await self.msg_mgr.update_message_assignments(self.msg_id, selected_db_ids)
        if success:
            QMessageBox.information(self, "Success", f"Message assigned to {len(selected_db_ids)} chats.")
            self.accept()
        else:
            QMessageBox.critical(self, "Error", "Failed to save assignments.")
            self.btn_save.setEnabled(True)
            self.btn_save.setText("Save Assignments")
