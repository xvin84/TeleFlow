from typing import Optional, Tuple, Any
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from teleflow.utils.logger import logger

class TeleflowClient:
    """Wrapper around Telethon's TelegramClient."""

    def __init__(self, phone: str, api_id: int, api_hash: str, session_string: Optional[str] = None) -> None:
        self.phone = phone
        self.api_id = api_id
        self.api_hash = api_hash
        self.session = StringSession(session_string)
        
        # We use a memory session for the auth flow if no string is provided.
        # Once authenticated, we export it.
        self.client = TelegramClient(
            self.session, 
            api_id=self.api_id, 
            api_hash=self.api_hash,
            app_version="teleflow v0.1.0",
            device_model="Desktop",
            system_version="Windows/Linux"
        )
        self._phone_code_hash: Optional[str] = None

    async def connect(self) -> bool:
        """Connect to Telegram servers."""
        logger.debug(f"Connecting Telethon client for {self.phone}")
        await self.client.connect()
        return bool(await self.client.is_user_authorized())

    async def disconnect(self) -> None:
        """Disconnect the client."""
        if self.client.is_connected():
            logger.debug(f"Disconnecting Telethon client for {self.phone}")
            await self.client.disconnect()

    async def send_code(self) -> Tuple[bool, str]:
        """
        Send SMS/Telegram code to the phone number.
        Returns:
            Tuple[bool, str]: (is_success, error_or_hash_message)
        """
        try:
            if not self.client.is_connected():
                await self.client.connect()
                
            result = await self.client.send_code_request(self.phone)
            self._phone_code_hash = result.phone_code_hash
            logger.info(f"Code sent to {self.phone}")
            return True, "Code sent successfully"
        except errors.FloodWaitError as e:
            logger.warning(f"FloodWait when sending code for {self.phone}: {e.seconds}s")
            return False, f"Слишком много попыток. Подождите {e.seconds} секунд."
        except Exception as e:
            logger.error(f"Failed to send code to {self.phone}: {e}")
            return False, str(e)

    async def sign_in_with_code(self, code: str) -> Tuple[bool, bool, str]:
        """
        Sign in with the received code.
        Returns:
            Tuple[bool, bool, str]: (is_success, requires_2fa, error_message)
        """
        if not self._phone_code_hash:
            return False, False, "Сначала необходимо запросить код."

        try:
            await self.client.sign_in(phone=self.phone, code=code, phone_code_hash=self._phone_code_hash)
            logger.info(f"Successfully signed in {self.phone}")
            return True, False, ""
        except errors.SessionPasswordNeededError:
            logger.info(f"2FA password needed for {self.phone}")
            return False, True, "Требуется пароль 2FA."
        except errors.PhoneCodeInvalidError:
            logger.warning(f"Invalid code entered for {self.phone}")
            return False, False, "Неверный код."
        except errors.PhoneCodeExpiredError:
            logger.warning(f"Code expired for {self.phone}")
            return False, False, "Срок действия кода истек."
        except Exception as e:
            logger.error(f"Failed to sign in with code for {self.phone}: {e}")
            return False, False, str(e)

    async def sign_in_with_password(self, password: str) -> Tuple[bool, str]:
        """
        Sign in with 2FA password.
        Returns:
            Tuple[bool, str]: (is_success, error_message)
        """
        try:
            await self.client.sign_in(password=password)
            logger.info(f"Successfully signed in {self.phone} with 2FA")
            return True, ""
        except errors.PasswordHashInvalidError:
            logger.warning(f"Invalid 2FA password for {self.phone}")
            return False, "Неверный пароль 2FA."
        except Exception as e:
            logger.error(f"Failed to sign in with 2FA for {self.phone}: {e}")
            return False, str(e)

    def export_session(self) -> str:
        """Export the session string for storage."""
        return str(self.session.save())

    async def get_all_dialogs(self) -> list[dict[str, Any]]:
        """
        Fetch all dialogs (chats, channels, users).
        Returns a list of dictionaries with chat info.
        """
        if not self.client.is_connected():
            await self.client.connect()
            
        dialogs = []
        try:
            # Depending on the account size, fetching all dialogs might take a moment.
            # Using iter_dialogs or get_dialogs from Telethon.
            async for dialog in self.client.iter_dialogs():
                chat_type = "User"
                if dialog.is_channel:
                    chat_type = "Channel"
                elif dialog.is_group:
                    chat_type = "Group"
                
                # Fetching access_hash isn't strictly necessary to just show them, 
                # but good for further MTProto requests.
                access_hash = getattr(dialog.entity, 'access_hash', None)
                
                dialogs.append({
                    "id": dialog.id,
                    "title": dialog.title or "Unknown",
                    "type": chat_type,
                    "access_hash": access_hash
                })
            
            logger.info(f"Fetched {len(dialogs)} dialogs for {self.phone}")
            return dialogs
            
        except Exception as e:
            logger.error(f"Failed to fetch dialogs for {self.phone}: {e}")
            return []
