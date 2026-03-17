import csv
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFileDialog, QMessageBox, QListWidget, QWidget
)
from typing import List, Tuple
from teleflow.utils.logger import logger
from teleflow.core.storage.db import db

class CSVMessageImportWizard(QDialog):
    """Wizard to bulk import message templates from a CSV."""
    
    def __init__(self, account_phone: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.account_phone = account_phone
        self.setWindowTitle("Import Messages from CSV")
        self.resize(600, 450)
        self._setup_ui()
        
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        
        lbl_info = QLabel(
            "Select a .csv file to bulk import message templates.\n"
            "Format: Title, Text Content, Media Path (Optional)"
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
        
        self.parsed_data: List[Tuple[str, str, str | None]] = []

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
                    if not row or (row_idx == 0 and 'title' in str(row[0]).lower()):
                        continue
                        
                    # Expecting: Title, Text Content, Media Path
                    title = row[0].strip() if len(row) > 0 else "Untitled"
                    text = row[1].strip() if len(row) > 1 else ""
                    media_path = row[2].strip() if len(row) > 2 else None
                    if media_path and not media_path.strip():
                        media_path = None
                    
                    self.parsed_data.append((title, text, media_path))
                    attach_text = "[Has Attachment]" if media_path else "[Text Only]"
                    self.list_preview.addItem(f"{title} - {attach_text}")
            
            if self.parsed_data:
                self.btn_import.setEnabled(True)
                logger.info(f"Parsed {len(self.parsed_data)} message templates from CSV.")
            else:
                QMessageBox.warning(self, "Warning", "No valid message data found in CSV.")
                self.btn_import.setEnabled(False)
                
        except Exception as e:
            logger.exception("Failed to parse CSV.")
            QMessageBox.critical(self, "Error", f"Failed to read CSV:\n{e}")

    import qasync
    @qasync.asyncSlot()
    async def _perform_import(self) -> None:
        success = 0
        try:
            for title, text, media_path in self.parsed_data:
                await db.execute(
                    """
                    INSERT INTO messages (account_phone, title, text_content, media_path)
                    VALUES (?, ?, ?, ?)
                    """,
                    (self.account_phone, title, text, media_path)
                )
                success += 1
                
            await db.commit()
            QMessageBox.information(self, "Success", f"Imported {success} message templates!")
            self.accept()
        except Exception as e:
            logger.error(f"Failed to import messages to DB: {e}")
            QMessageBox.critical(self, "Error", f"Database error during import:\n{e}")
