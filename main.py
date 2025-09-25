import os
# Suppress gRPC/absl verbosity before any SDK imports
os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
os.environ.setdefault("GRPC_LOG_SEVERITY_LEVEL", "ERROR")
os.environ.setdefault("GLOG_minloglevel", "3")
os.environ.setdefault("GLOG_logtostderr", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from dotenv import load_dotenv
import _config
from _config.logging_config import setup_logging


load_dotenv()

# Configure logging early (before importing routers/services)
setup_logging(level=logging.INFO)  # Temporarily enable debug logging
logger = logging.getLogger(__name__)

# Delayed imports to ensure logging/env suppression is in effect
from services.virtual_tryon_service import VirtualTryOnService
from api.routers.threads import router as threads_router
from api.routers.virtual_tryon import router as virtual_tryon_router
from api.routers.avatars import router as avatars_router
from api.routers.prompt_suggestions import router as prompt_suggestions_router
from api.routers.outfits import router as outfits_router
from api.routers.explore_ideas import router as explore_ideas_router


# Initialize services
virtual_tryon_service = VirtualTryOnService()

@asynccontextmanager
async def lifespan(app: FastAPI):
	"""Handle application startup and shutdown events"""
	# Startup
	logger.info("\n\n🚀 🚀 🚀 🚀 🚀 SERVER STARTING UP 🚀 🚀 🚀 🚀 🚀")
	

	yield
	
	# Shutdown
	logger.info("\n\n🛑 🛑 🛑 🛑 🛑 SERVER SHUTTING DOWN 🛑 🛑 🛑 🛑 🛑")

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
app.include_router(avatars_router)
app.include_router(prompt_suggestions_router)
app.include_router(outfits_router)
app.include_router(explore_ideas_router)


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
			"/api/prompt-suggestions/{user_id}/generate",
			"/api/outfits/{outfit_id}/search-and-rank",
		"/api/explore-ideas/generate-research",
		]
	}


if __name__ == "__main__":
	import uvicorn
	uvicorn.run(
		"main:app",
		host="0.0.0.0",
		port=8000,
		reload=True,  # Disabled auto-reload - manual restart required for code changes
		log_level="info",
		access_log=False,
	) 