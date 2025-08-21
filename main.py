from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
from dotenv import load_dotenv
import _config
from _config.logging_config import setup_logging

from services.virtual_tryon_service import VirtualTryOnService
# from utils.image_processing.face_injector import FaceInjector  # Lazy-imported in lifespan
from api.routers.threads import router as threads_router
from api.routers.virtual_tryon import router as virtual_tryon_router


load_dotenv()

# Configure logging
setup_logging(level=logging.INFO)  # Temporarily enable debug logging
logger = logging.getLogger(__name__)

# Initialize services
virtual_tryon_service = VirtualTryOnService()

@asynccontextmanager
async def lifespan(app: FastAPI):
	"""Handle application startup and shutdown events"""
	# Startup
	logger.info("🚀 AI Stylist Server starting up...")
	
	# Set up InsightFace persistent storage path BEFORE importing FaceInjector
	if _config.FACE_SWAP_ENABLED:
		insightface_home = os.getenv("INSIGHTFACE_HOME", os.path.expanduser("~/.insightface"))
		os.environ["INSIGHTFACE_HOME"] = insightface_home
		
		# Preload FaceInjector model at startup to avoid loading delays during requests
		try:
			from utils.image_processing.face_injector import FaceInjector
			FaceInjector.instance()
		except Exception as e:
			logger.error(f"❌ Failed to preload FaceInjector model: {e}")
			# Continue startup even if face model fails to load
	else:
		logger.info("🧯 FACE_SWAP_ENABLED is false; skipping InsightFace setup and FaceInjector preload")
	
	yield
	# Shutdown
	logger.info("🔄 AI Stylist Server shutting down...")

app = FastAPI(lifespan=lifespan, title="AI Stylist API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
	CORSMiddleware,
	allow_origins=_config.CORS_ORIGINS,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

# Register routers
app.include_router(threads_router)
app.include_router(virtual_tryon_router)


@app.get("/")
async def health_check():
	return {"status": "healthy", "service": "AI Stylist API", "version": "1.0.0"}

@app.get("/health")
async def detailed_health_check():
	return {
		"status": "healthy",
		"service": "AI Stylist API",
		"version": "1.0.0",
		"cors_origins": _config.CORS_ORIGINS,
		"endpoints": [
			"/api/threads",
			"/api/virtual-try-on",
		]
	}


if __name__ == "__main__":
	import uvicorn
	logger.info("🎯 Starting AI Stylist Server locally...")
	uvicorn.run(
		"main:app",
		host="0.0.0.0",
		port=8000,
		reload=True,
		log_level="info",
		access_log=False,
	) 