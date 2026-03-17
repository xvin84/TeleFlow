import bcrypt
from teleflow.utils.logger import logger

def hash_password(password: str) -> str:
    """
    Hash a password for storing.
    
    Args:
        password: Plain text password.
        
    Returns:
        The bcrypt hash string.
    """
    try:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to hash password: {e}")
        raise

def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.
    
    Args:
        password: Plain text password.
        hashed_password: The bcrypt hash string.
        
    Returns:
        True if the password matches, False otherwise.
    """
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        logger.warning("Invalid hash format encountered during password verification.")
        return False
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False
