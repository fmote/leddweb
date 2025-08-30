from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure, ConfigurationError
from pymongo.server_api import ServerApi
import os
from dotenv import load_dotenv
import base64
from typing import Tuple, Optional
import logging
from functools import lru_cache

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class MongoDBConnection:
    """Singleton class to manage MongoDB connection"""
    _instance = None
    _client = None
    _db = None
    _connection_string = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBConnection, cls).__new__(cls)
        return cls._instance
    
    @classmethod
    def get_connection_string(cls) -> Optional[str]:
        """Get decoded MongoDB connection string"""
        if cls._connection_string is None:
            try:
                b64_string = os.getenv('MONGODB_URI')
                if not b64_string:
                    logger.error("MONGODB_URI environment variable not found")
                    return None
                cls._connection_string = base64.b64decode(b64_string).decode('utf-8')
            except Exception as e:
                logger.error(f"Failed to decode MongoDB URI: {e}")
                return None
        return cls._connection_string
    
    @classmethod
    def get_connection_options(cls) -> dict:
        """Get MongoDB connection options"""
        return {
            "tls": False,
            "retryWrites": False,
            "serverSelectionTimeoutMS": 3000,  # Reduced from 5000 to 3000ms
            "connectTimeoutMS": 5000,          # Reduced from 10000 to 5000ms
            "maxPoolSize": 100,                # Increased from 50 to 100
            "minPoolSize": 20,                 # Increased from 10 to 20
            "maxIdleTimeMS": 60000,            # Increased from 30000 to 60000ms
            "server_api": ServerApi('1'),      # Use latest stable API version
            "appName": "VibeNiteBot"           # Add application name for monitoring
        }
    
    @classmethod
    @lru_cache(maxsize=1)
    def connect(cls) -> Tuple[Optional[MongoClient], Optional[object]]:
        """Establish connection to MongoDB with caching"""
        try:
            # Get connection string
            connection_string = cls.get_connection_string()
            if not connection_string:
                return None, None
            
            # Get connection options
            client_options = cls.get_connection_options()
            
            # Create MongoDB client
            client = MongoClient(connection_string, **client_options)
            
            # Test connection
            client.admin.command('ping')
            
            # Get database
            db = client['botdb']
            
            logger.info("Successfully connected to MongoDB")
            return client, db
            
        except ServerSelectionTimeoutError:
            # Avoid leaking server IP/port in logs
            logger.error("Server selection timeout")
            return None, None
        except ConnectionFailure:
            # Avoid leaking server IP/port in logs
            logger.error("Connection failure")
            return None, None
        except ConfigurationError:
            # Keep message generic to avoid leaking sensitive details
            logger.error("MongoDB configuration error")
            return None, None
        except Exception:
            # Keep message generic to avoid leaking sensitive details
            logger.error("Unexpected error connecting to MongoDB")
            return None, None
    
    @classmethod
    def get_client(cls) -> Optional[MongoClient]:
        """Get MongoDB client instance"""
        if cls._client is None:
            cls._client, cls._db = cls.connect()
        return cls._client
    
    @classmethod
    def get_db(cls) -> Optional[object]:
        """Get MongoDB database instance"""
        if cls._db is None:
            cls._client, cls._db = cls.connect()
        return cls._db
    
    @classmethod
    def close(cls) -> None:
        """Close MongoDB connection"""
        if cls._client:
            try:
                cls._client.close()
                logger.info("MongoDB connection closed")
            except Exception as e:
                logger.error(f"Error closing MongoDB connection: {e}")
            finally:
                cls._client = None
                cls._db = None

def connect_to_mongodb() -> Tuple[Optional[MongoClient], Optional[object]]:
    """Connect to MongoDB using the singleton connection manager"""
    return MongoDBConnection.connect()