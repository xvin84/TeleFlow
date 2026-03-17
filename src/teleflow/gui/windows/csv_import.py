import csv
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFileDialog, QMessageBox, QListWidget, QWidget
)
from typing import List, Tuple
from teleflow.utils.logger import logger
from teleflow.core.storage.db import db

class CSVImportWizard(QDialog):
    """Wizard to bulk import chat targets (phone, username, channel link) from a CSV."""
    
    def __init__(self, account_phone: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.account_phone = account_phone
        self.setWindowTitle("Import Chats from CSV")
        self.resize(500, 400)
        self._setup_ui()
        
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        
        lbl_info = QLabel(
            "Select a .csv file to bulk import chat targets.\n"
            "Format: Target (Username/Phone/Link), Title, Type (User/Group/Channel)"
        )
        layout.addWidget(lbl_info)
        
        # File selection
        file_layout = QHBoxLayout()
        self.inp_file = QLineEdit()
        self.inp_file.setReadOnly(True)
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_file)
        
        file_layout.addWidget(self.inp_file)
        file_layout.addWidget(btn_browse)
        layout.addLayout(file_layout)
        
        # Preview list
        layout.addWidget(QLabel("Preview:"))
        self.list_preview = QListWidget()
        layout.addWidget(self.list_preview)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        self.btn_import = QPushButton("Import")
        self.btn_import.setEnabled(False)
        self.btn_import.clicked.connect(self._perform_import)
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self.btn_import)
        layout.addLayout(btn_layout)
        
        self.parsed_data: List[Tuple[str, str, str]] = []

    def _browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV", "", "CSV Files (*.csv)"
        )
        if file_path:
            self.inp_file.setText(file_path)
            self._parse_csv(file_path)

    def _parse_csv(self, file_path: str) -> None:
        self.list_preview.clear()
        self.parsed_data.clear()
        
        try:
            with open(file_path, mode="r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row_idx, row in enumerate(reader):
                    # Skip empty rows or header (simple check: if first word is 'target' or 'link')
                    if not row or (row_idx == 0 and 'target' in str(row[0]).lower()):
                        continue
                        
                    # Expecting: Target, Title, Type
                    target = row[0].strip() if len(row) > 0 else "Unknown"
                    title = row[1].strip() if len(row) > 1 else target
                    chat_type = row[2].strip() if len(row) > 2 else "User"
                    
                    self.parsed_data.append((target, title, chat_type))
                    self.list_preview.addItem(f"{title} [{chat_type}] - {target}")
            
            if self.parsed_data:
                self.btn_import.setEnabled(True)
                logger.info(f"Parsed {len(self.parsed_data)} rows from CSV.")
            else:
                QMessageBox.warning(self, "Warning", "No valid data found in CSV.")
                self.btn_import.setEnabled(False)
                
        except Exception as e:
            logger.exception("Failed to parse CSV.")
            QMessageBox.critical(self, "Error", f"Failed to read CSV:\n{e}")

    # Note: Telethon requires MTProto resolution to get actual `chat_id`s from usernames/links.
    # For now, we will add them with temporary IDs or just rely on TeleflowClient later to resolve them.
    # We use a negative hash-based ID for unverified CSV imports.
    import qasync
    @qasync.asyncSlot()
    async def _perform_import(self) -> None:
        import hashlib
        
        success = 0
        try:
            for target, title, chat_type in self.parsed_data:
                # Generate a deterministic negative fake ID for unverified links
                fake_id = -int(hashlib.md5(target.encode()).hexdigest(), 16) % (10**9)
                
                await db.execute(
                    """
                    INSERT INTO chats (account_phone, chat_id, title, type, access_hash)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(account_phone, chat_id) DO UPDATE SET title=excluded.title
                    """,
                    (self.account_phone, fake_id, f"{title} (CSV)", chat_type, 0) # 0 means unverified
                )
                success += 1
                
            await db.commit()
            QMessageBox.information(self, "Success", f"Imported {success} chats!")
            self.accept()
        except Exception as e:
            logger.error(f"Failed to import chats to DB: {e}")
            QMessageBox.critical(self, "Error", f"Database error during import:\n{e}")
