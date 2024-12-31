import os
import logging
import asyncio
from aiohttp import ClientSession, ClientError
import json
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Index
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import random
import time
from functools import lru_cache
import difflib
from typing import Dict, List, Tuple
import redis  # For scalable caching
from aiopg.sa import create_engine as create_async_engine
from fastapi import FastAPI, Body
from mangum import Mangum  # For AWS Lambda, but works with Vercel's serverless too

# Configuration from environment variables
DATABASE_URL = os.getenv('DATABASE_URL')
API_URL = os.getenv('EXTERNAL_API_URL')
ACADEMIC_RESOURCES_API = os.getenv('ACADEMIC_RESOURCES_API')
GOOGLE_CALENDAR_CREDS = os.getenv('GOOGLE_CALENDAR_CREDS')
QUIZ_API_URL = os.getenv('QUIZ_API_URL')

# Redis connection using environment variables
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

SCOPES = ['https://www.googleapis.com/auth/calendar']

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Use StreamHandler for logging in serverless environments
    ]
)
logger = logging.getLogger(__name__)

# Database setup
Base = declarative_base()

class Topic(Base):
    __tablename__ = 'topics'
    id = Column(Integer, primary_key=True)
    sector = Column(String, index=True)
    content = Column(String)
    further_reading = Column(String)
    last_update = Column(DateTime, default=datetime.datetime.utcnow)

class UserProgress(Base):
    __tablename__ = 'user_progress'
    id = Column(Integer, primary_key=True)
    sector = Column(String)
    last_study_date = Column(DateTime)
    performance = Column(Float)
    notes = Column(String)

class SearchHistory(Base):
    __tablename__ = 'search_history'
    id = Column(Integer, primary_key=True)
    query = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

Index('ix_topics_sector', Topic.sector)

app = FastAPI()

# Scalable caching with Redis
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, password=REDIS_PASSWORD)

async def init_async_db():
    global async_engine
    async_engine = await create_async_engine(DATABASE_URL)

async def get_engine():
    global async_engine
    if async_engine is None:
        await init_async_db()
    return async_engine

@app.on_event("startup")
async def startup_event():
    await get_engine()

async def fetch_api_data(sector):
    try:
        async with ClientSession() as session:
            params = {'sector': sector}
            async with session.get(API_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    redis_client.setex(f'api_{sector}', 3600, json.dumps(data))  # Cache for 1 hour
                    return data
                else:
                    raise ValueError(f"API returned status code {response.status}")
    except (ClientError, ValueError, json.JSONDecodeError) as e:
        logger.error(f"Error fetching API data for sector {sector}: {str(e)}")
        return None

# Placeholder for other async functions

async def get_advanced_topic_content(question, sector, offline_mode=False):
    try:
        engine = await get_engine()
        async with engine.acquire() as connection:
            if not offline_mode and await should_fetch_from_api(sector, connection):
                await update_topic_from_api(sector)
            
            result = await connection.execute("SELECT content, further_reading FROM topics WHERE sector = :sector", {'sector': sector})
            topic = await result.fetchone()
            if not topic:
                return "I'm sorry, I don't have information on that sector.", None
            
            context = topic.content
            if not offline_mode:
                academic_data = redis_client.get(f'academic_{sector}')
                if academic_data is None:
                    academic_data = await fetch_academic_resources(sector)
                if academic_data:
                    academic_data = json.loads(academic_data)
                    context += "\n" + "\n".join([item['summary'] for item in academic_data])

            # Placeholder for NLP model response
            return "Answer based on the context", topic.further_reading
    except Exception as e:
        logger.error(f"Error retrieving content for sector {sector}: {e}")
        return f"An error occurred: {str(e)}", None

async def should_fetch_from_api(sector, connection):
    result = await connection.execute("SELECT last_update FROM topics WHERE sector = :sector", {'sector': sector})
    topic = await result.fetchone()
    return not topic or (datetime.datetime.utcnow() - topic.last_update).days > 7

async def advanced_search(query, user_preferences=None) -> List[Tuple[str, str, float]]:
    engine = await get_engine()
    async with engine.acquire() as connection:
        results = []
        async for topic in await connection.execute("SELECT sector, content, last_update FROM topics"):
            score = calculate_relevance_score(query, topic.content, topic.last_update, user_preferences)
            if score > 0:
                results.append((topic.sector, topic.content, score))
        return sorted(results, key=lambda x: x[2], reverse=True)[:10]

def calculate_relevance_score(query, content, last_update, user_preferences=None):
    # Simplified relevance calculation
    return 0.5  # Placeholder score

@app.post("/get_topic_content")
async def get_topic_content_route(data: dict = Body(...)):
    question = data.get('question', '')
    sector = data.get('sector', '')
    offline_mode = data.get('offline_mode', False)
    answer, link = await get_advanced_topic_content(question, sector, offline_mode)
    return {"answer": answer, "link": link}

@app.post("/advanced_search")
async def advanced_search_route(data: dict = Body(...)):
    query = data.get('query', '')
    user_preferences = data.get('preferences', None)
    results = await advanced_search(query, user_preferences)
    return [{"sector": sector, "content": content[:200] + '...' if len(content) > 200 else content, "score": score} for sector, content, score in results]

# Using Mangum to adapt FastAPI for serverless environments like Vercel
handler = Mangum(app)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)