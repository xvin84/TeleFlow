from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QWidget, QLabel, QLineEdit, QPushButton, QMessageBox, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from teleflow.i18n import t
from teleflow.core.telegram.client import TeleflowClient
from teleflow.core.account_manager import AccountManager
from teleflow.utils.logger import logger
from teleflow.gui.styles import theme_manager
import qasync


class LoginWindow(QDialog):
    """
    Wizard for adding a new Telegram account.
    Steps:
    0: API ID / API Hash
    1: Phone
    2: Confirmation Code
    3: 2FA Password
    """

    account_added = pyqtSignal(str)

    def __init__(
        self,
        account_manager: AccountManager,
        cancellable: bool = True,
        is_first_launch: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.account_manager = account_manager
        self.cancellable = cancellable
        self.is_first_launch = is_first_launch
        self.client: TeleflowClient | None = None

        self._temp_api_id = 0
        self._temp_api_hash = ""
        self._temp_phone = ""

        self.setWindowTitle(t("login.title"))
        self.setFixedSize(400, 550)
        self.setModal(True)
        # Use live QSS so it respects the currently active theme
        self.setStyleSheet(theme_manager.login_qss())

        if not self.cancellable:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        self._setup_ui()

    def _create_page_header(self, layout: QVBoxLayout, title_key: str, desc_key: str) -> None:
        title = QLabel(t(title_key))
        title.setObjectName("TitleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel(t(desc_key))
        desc.setObjectName("DescLabel")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setOpenExternalLinks(True)

        layout.addWidget(title)
        layout.addWidget(desc)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        self._init_page_0_api()
        self._init_page_1_phone()
        self._init_page_2_code()
        self._init_page_3_password()

        self.stack.setCurrentIndex(0)

    # --- Step 0: API Credentials ---
    def _init_page_0_api(self) -> None:
        page = QWidget()
        ly = QVBoxLayout(page)
        ly.setContentsMargins(35, 40, 35, 30)

        self._create_page_header(ly, "login.api_title", "login.api_desc")

        self.inp_api_id = QLineEdit()
        self.inp_api_id.setPlaceholderText(
            t("login.api_id_label") + " (" + t("login.api_id_placeholder") + ")"
        )
        ly.addWidget(self.inp_api_id)

        ly.addSpacing(10)

        self.inp_api_hash = QLineEdit()
        self.inp_api_hash.setPlaceholderText(
            t("login.api_hash_label") + " (" + t("login.api_hash_placeholder") + ")"
        )
        ly.addWidget(self.inp_api_hash)

        ly.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        self.btn_next_0 = QPushButton(t("login.btn_next"))
        self.btn_next_0.setObjectName("NextBtn")
        self.btn_next_0.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_next_0.clicked.connect(self._on_api_submit)
        ly.addWidget(self.btn_next_0)

        if self.cancellable:
            ly.addSpacing(10)
            btn_text = t("login.btn_skip") if self.is_first_launch else t("login.btn_cancel")
            btn_cancel = QPushButton(btn_text)
            btn_cancel.setObjectName("CancelBtn")
            btn_cancel.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_cancel.clicked.connect(self.reject)
            ly.addWidget(btn_cancel)

        self.stack.addWidget(page)

    # --- Step 1: Phone Number ---
    def _init_page_1_phone(self) -> None:
        page = QWidget()
        ly = QVBoxLayout(page)
        ly.setContentsMargins(35, 40, 35, 30)

        self._create_page_header(ly, "login.phone_title", "login.phone_desc")

        self.inp_phone = QLineEdit()
        self.inp_phone.setPlaceholderText(t("login.phone_placeholder"))
        ly.addWidget(self.inp_phone)

        ly.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        self.btn_next_1 = QPushButton(t("login.btn_next"))
        self.btn_next_1.setObjectName("NextBtn")
        self.btn_next_1.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_next_1.clicked.connect(self._on_phone_submit)
        ly.addWidget(self.btn_next_1)

        ly.addSpacing(10)
        btn_back = QPushButton(t("login.btn_back"))
        btn_back.setObjectName("LinkBtn")
        btn_back.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        hly = QHBoxLayout()
        hly.addWidget(btn_back, alignment=Qt.AlignmentFlag.AlignCenter)
        ly.addLayout(hly)

        self.stack.addWidget(page)

    # --- Step 2: Code ---
    def _init_page_2_code(self) -> None:
        page = QWidget()
        ly = QVBoxLayout(page)
        ly.setContentsMargins(35, 40, 35, 30)

        self._create_page_header(ly, "login.code_title", "login.code_desc")

        self.inp_code = QLineEdit()
        self.inp_code.setPlaceholderText("----")
        self.inp_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.inp_code.setStyleSheet("font-size: 24px; letter-spacing: 5px;")
        ly.addWidget(self.inp_code)

        ly.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        self.btn_next_2 = QPushButton(t("login.btn_next"))
        self.btn_next_2.setObjectName("NextBtn")
        self.btn_next_2.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_next_2.clicked.connect(self._on_code_submit)
        ly.addWidget(self.btn_next_2)

        ly.addSpacing(10)
        btn_back = QPushButton(t("login.btn_back"))
        btn_back.setObjectName("LinkBtn")
        btn_back.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        hly = QHBoxLayout()
        hly.addWidget(btn_back, alignment=Qt.AlignmentFlag.AlignCenter)
        ly.addLayout(hly)

        self.stack.addWidget(page)

    # --- Step 3: Password ---
    def _init_page_3_password(self) -> None:
        page = QWidget()
        ly = QVBoxLayout(page)
        ly.setContentsMargins(35, 40, 35, 30)

        self._create_page_header(ly, "login.password_title", "login.password_desc")

        self.inp_pwd = QLineEdit()
        self.inp_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_pwd.setPlaceholderText(t("login.password_label"))
        ly.addWidget(self.inp_pwd)

        ly.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        self.btn_next_3 = QPushButton(t("login.btn_next"))
        self.btn_next_3.setObjectName("NextBtn")
        self.btn_next_3.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_next_3.clicked.connect(self._on_pwd_submit)
        ly.addWidget(self.btn_next_3)

        ly.addSpacing(10)
        btn_back = QPushButton(t("login.btn_back"))
        btn_back.setObjectName("LinkBtn")
        btn_back.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        hly = QHBoxLayout()
        hly.addWidget(btn_back, alignment=Qt.AlignmentFlag.AlignCenter)
        ly.addLayout(hly)

        self.stack.addWidget(page)

    # --- Handlers ---

    def _on_api_submit(self) -> None:
        api_id_text = self.inp_api_id.text().strip()
        api_hash = self.inp_api_hash.text().strip()

        if not api_id_text or not api_hash:
            QMessageBox.warning(self, "Ошибка", t("login.warning_empty"))
            return

        try:
            self._temp_api_id = int(api_id_text)
            self._temp_api_hash = api_hash
            self.stack.setCurrentIndex(1)
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "API ID должен быть числом.")

    @qasync.asyncSlot()
    async def _on_phone_submit(self) -> None:
        phone = self.inp_phone.text().strip()

        if not phone:
            QMessageBox.warning(self, "Ошибка", t("login.warning_empty"))
            return

        self.btn_next_1.setEnabled(False)
        self.btn_next_1.setText("ОТПРАВКА...")

        self._temp_phone = phone
        self.client = TeleflowClient(self._temp_phone, self._temp_api_id, self._temp_api_hash)
        is_success, msg = await self.client.send_code()

        if is_success:
            self.inp_code.clear()
            self.stack.setCurrentIndex(2)
        else:
            QMessageBox.critical(self, "Ошибка", msg)

        self.btn_next_1.setEnabled(True)
        self.btn_next_1.setText(t("login.btn_next"))

    @qasync.asyncSlot()
    async def _on_code_submit(self) -> None:
        code = self.inp_code.text().strip()
        if not code or self.client is None:
            return

        self.btn_next_2.setEnabled(False)
        self.btn_next_2.setText("ПРОВЕРКА...")

        is_success, req_2fa, msg = await self.client.sign_in_with_code(code)

        if is_success:
            await self._finish_login()
        elif req_2fa:
            self.inp_pwd.clear()
            self.stack.setCurrentIndex(3)
        else:
            QMessageBox.critical(self, "Ошибка", msg)

        self.btn_next_2.setEnabled(True)
        self.btn_next_2.setText(t("login.btn_next"))

    @qasync.asyncSlot()
    async def _on_pwd_submit(self) -> None:
        pwd = self.inp_pwd.text().strip()
        if not pwd or self.client is None:
            return

        self.btn_next_3.setEnabled(False)
        self.btn_next_3.setText("ПРОВЕРКА...")

        is_success, msg = await self.client.sign_in_with_password(pwd)

        if is_success:
            await self._finish_login()
        else:
            QMessageBox.critical(self, "Ошибка", msg)

        self.btn_next_3.setEnabled(True)
        self.btn_next_3.setText(t("login.btn_next"))

    async def _finish_login(self) -> None:
        if not self.client:
            return
        try:
            session_str = self.client.export_session()
            await self.account_manager.add_account(
                self.client.phone,
                self.client.api_id,
                self.client.api_hash,
                session_str,
            )
            self.account_added.emit(self.client.phone)
            self.accept()
        except Exception as e:
            logger.exception("Failed to store account post-login.")
            QMessageBox.critical(self, "Ошибка базы данных", str(e))