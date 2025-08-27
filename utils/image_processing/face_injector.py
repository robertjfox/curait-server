import cv2
import numpy as np
import insightface
from insightface.app import FaceAnalysis
from insightface.model_zoo import get_model
import onnxruntime as ort
import hashlib
import logging
from typing import Optional, Dict, Tuple, Union
from io import BytesIO
from pathlib import Path
from threading import RLock
from _config.master_config import (
    FACE_DETECTION_SIZE, 
    FACE_DETECTION_THRESHOLD,
    FACE_MIN_SIZE,
    FACE_MIN_CONFIDENCE,
    INSIGHTFACE_HOME
)

logger = logging.getLogger(__name__)


class FaceInjector:
    _instance = None
    _initialized = False
    
    def __init__(self):
        if not FaceInjector._initialized:
            self._init_models()
            self._face_cache: Dict[str, np.ndarray] = {}  # Cache for source face embeddings
            self._lock = RLock()
            FaceInjector._initialized = True
    
    @classmethod
    def instance(cls):
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _init_models(self):
        """Initialize InsightFace models"""
        
        # Suppress all ONNX Runtime logs (Applied providers, etc.)
        import onnxruntime as ort
        ort.set_default_logger_severity(3)  # 3=ERROR, 4=FATAL - hides INFO/WARNING
        
        # Suppress verbose third-party logging
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning)
        
        # Silence specific third-party loggers that might output raw data
        import logging as stdlib_logging
        for noisy_lib in ['insightface', 'onnxruntime', 'onnx', 'cv2', 'opencv']:
            stdlib_logging.getLogger(noisy_lib).setLevel(stdlib_logging.ERROR)
            stdlib_logging.getLogger(noisy_lib).propagate = False
        
        # Use context manager to suppress stdout/stderr during model initialization
        # This catches hard-coded prints like "find model:", "set det-size:", etc.
        import contextlib
        import sys
        import os
        
        with open(os.devnull, "w") as devnull, \
             contextlib.redirect_stdout(devnull), \
             contextlib.redirect_stderr(devnull):
            
            # Set ONNX providers based on available hardware
            providers = ['CPUExecutionProvider']
            if ort.get_device() == 'GPU':
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            
            # Initialize face analysis with configurable detection quality
            self.app = FaceAnalysis(name='buffalo_l', providers=providers)
            self.app.prepare(
                ctx_id=0, 
                det_size=(FACE_DETECTION_SIZE, FACE_DETECTION_SIZE), 
                det_thresh=FACE_DETECTION_THRESHOLD
            )
            
            # Initialize face swapper
            try:
                # Use configured InsightFace home directory
                insightface_models_dir = os.path.join(os.path.expanduser(INSIGHTFACE_HOME), 'models')
                local_model_path = os.path.join(insightface_models_dir, 'inswapper_128.onnx')
                
                if os.path.exists(local_model_path):
                    # Load the model directly using the insightface approach
                    import onnxruntime
                    from insightface.model_zoo.inswapper import INSwapper
                    self.swapper = INSwapper(local_model_path)
                else:
                    # Ensure InsightFace home directory is set before downloading
                    os.environ['INSIGHTFACE_HOME'] = os.path.expanduser(INSIGHTFACE_HOME)
                    model_path = get_model('inswapper_128.onnx', download=True, download_zip=False)
                    self.swapper = insightface.model_zoo.get_model(model_path, providers=providers)
                
                self.swapper_available = True
            except Exception as e:
                # Restore stderr temporarily for this error log
                print(f"[ ⚠️  VTON ] Failed to load face swapping model: {type(e).__name__}: {str(e)[:100]}...", file=sys.stderr)
                self.swapper = None
                self.swapper_available = False
        
    
    def _get_face_key(self, source_bytes: bytes) -> str:
        """Generate cache key from source image bytes"""
        return hashlib.md5(source_bytes).hexdigest()
    
    def _extract_face_embedding(self, img_bgr: np.ndarray) -> Optional[np.ndarray]:
        """Extract face embedding from image with quality filtering and alignment scoring"""
        faces = self.app.get(img_bgr)
        if not faces:
            return None
        
        # Filter faces by quality and size for better swapping results
        quality_faces = []
        for face in faces:
            # Calculate face area
            bbox_area = (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1])
            
            # Filter out small faces based on configuration
            if bbox_area < FACE_MIN_SIZE:
                continue
                
            # Check face detection confidence if available
            if hasattr(face, 'det_score') and face.det_score < FACE_MIN_CONFIDENCE:
                continue
            
            # Calculate alignment quality score for better face selection
            alignment_score = self._calculate_face_alignment_score(face)
            
            quality_faces.append((face, bbox_area, alignment_score))
        
        if not quality_faces:
            # Fallback to any detected face if no quality faces found
            largest_face = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
            return largest_face
        
        # Select best face based on combined score of size and alignment
        # Weight: 40% alignment quality, 60% face size (larger faces generally better for swapping)
        best_face = max(quality_faces, key=lambda x: (x[2] * 0.4) + (x[1] / max(f[1] for f in quality_faces) * 0.6))
        return best_face[0]
    
    def _calculate_face_alignment_score(self, face) -> float:
        """
        Calculate alignment quality score for a detected face.
        Higher score means better alignment (more frontal, less rotation).
        """
        score = 1.0
        
        # Check if landmarks are available for pose analysis
        if hasattr(face, 'kps') and face.kps is not None and len(face.kps) >= 5:
            landmarks = face.kps
            
            # Calculate face pose indicators
            # Landmarks order: left_eye, right_eye, nose, left_mouth, right_mouth
            left_eye = landmarks[0]
            right_eye = landmarks[1] 
            nose = landmarks[2]
            left_mouth = landmarks[3]
            right_mouth = landmarks[4]
            
            # 1. Eye level alignment (horizontal alignment)
            eye_y_diff = abs(left_eye[1] - right_eye[1])
            eye_distance = np.sqrt((left_eye[0] - right_eye[0])**2 + (left_eye[1] - right_eye[1])**2)
            if eye_distance > 0:
                eye_alignment_ratio = 1.0 - min(eye_y_diff / eye_distance, 1.0)
                score *= (0.5 + 0.5 * eye_alignment_ratio)  # Penalty for tilted faces
            
            # 2. Nose centrality (frontal pose indicator)
            eye_center_x = (left_eye[0] + right_eye[0]) / 2
            mouth_center_x = (left_mouth[0] + right_mouth[0]) / 2
            face_center_x = (eye_center_x + mouth_center_x) / 2
            
            # Nose should be close to face center for frontal pose
            nose_offset = abs(nose[0] - face_center_x)
            face_width = abs(right_eye[0] - left_eye[0])
            if face_width > 0:
                nose_centrality = 1.0 - min(nose_offset / (face_width * 0.5), 1.0)
                score *= (0.7 + 0.3 * nose_centrality)  # Bonus for frontal faces
            
            # 3. Mouth alignment (another frontal indicator)
            mouth_y_diff = abs(left_mouth[1] - right_mouth[1])
            mouth_distance = np.sqrt((left_mouth[0] - right_mouth[0])**2 + (left_mouth[1] - right_mouth[1])**2)
            if mouth_distance > 0:
                mouth_alignment_ratio = 1.0 - min(mouth_y_diff / mouth_distance, 1.0)
                score *= (0.8 + 0.2 * mouth_alignment_ratio)
        
        # 4. Face detection confidence bonus
        if hasattr(face, 'det_score') and face.det_score is not None:
            confidence_bonus = min(face.det_score, 1.0)
            score *= (0.8 + 0.2 * confidence_bonus)
        
        # 5. Face aspect ratio penalty for extreme ratios
        if hasattr(face, 'bbox') and face.bbox is not None:
            face_width = face.bbox[2] - face.bbox[0]
            face_height = face.bbox[3] - face.bbox[1]
            if face_height > 0:
                aspect_ratio = face_width / face_height
                # Ideal face aspect ratio is around 0.75-0.85
                ideal_ratio = 0.8
                ratio_deviation = abs(aspect_ratio - ideal_ratio) / ideal_ratio
                aspect_penalty = max(0.5, 1.0 - ratio_deviation)
                score *= aspect_penalty
        
        return max(0.1, min(1.0, score))  # Clamp between 0.1 and 1.0
    
    def _bytes_to_bgr(self, image_bytes: Union[bytes, BytesIO]) -> np.ndarray:
        """Convert image bytes to BGR numpy array"""
        if isinstance(image_bytes, BytesIO):
            image_bytes = image_bytes.getvalue()
        
        # Decode image from bytes
        nparr = np.frombuffer(image_bytes, np.uint8)
        img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img_bgr is None:
            raise ValueError("Failed to decode image from bytes")
        
        return img_bgr
    
    def _bgr_to_bytes(self, img_bgr: np.ndarray, format: str = '.jpg') -> bytes:
        """Convert BGR numpy array to image bytes"""
        success, encoded_img = cv2.imencode(format, img_bgr)
        if not success:
            raise ValueError("Failed to encode image to bytes")
        return encoded_img.tobytes()
    
    def swap(
        self, 
        source_key: str, 
        source_bytes: Union[bytes, BytesIO], 
        target_bytes: Union[bytes, BytesIO]
    ) -> np.ndarray:
        with self._lock:
            # Check if swapper is available
            if not self.swapper_available:
                return self._bytes_to_bgr(target_bytes)
            # Convert inputs to numpy arrays
            if isinstance(source_bytes, BytesIO):
                source_bytes = source_bytes.getvalue()
            if isinstance(target_bytes, BytesIO):
                target_bytes = target_bytes.getvalue()
                
            target_bgr = self._bytes_to_bgr(target_bytes)
            
            # Check cache for source face embedding
            cache_key = f"{source_key}_{self._get_face_key(source_bytes)}"
            
            if cache_key not in self._face_cache:
                source_bgr = self._bytes_to_bgr(source_bytes)
                source_face = self._extract_face_embedding(source_bgr)
                
                if source_face is None:
                    return target_bgr  # Return original if no face detected
                
                self._face_cache[cache_key] = source_face
            
            source_face = self._face_cache[cache_key]
            
            # Get target faces
            target_faces = self.app.get(target_bgr)
            if not target_faces:
                return target_bgr  # Return original if no face detected
            
            # Swap each detected face with quality prioritization
            result_img = target_bgr.copy()
            
            # Sort target faces by alignment quality and size for better results
            target_face_scores = []
            for target_face in target_faces:
                bbox_area = (target_face.bbox[2] - target_face.bbox[0]) * (target_face.bbox[3] - target_face.bbox[1])
                alignment_score = self._calculate_face_alignment_score(target_face)
                # Combined score: 50% alignment, 50% size for target faces
                combined_score = (alignment_score * 0.5) + (bbox_area * 0.5 / max(
                    (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]) for f in target_faces
                ))
                target_face_scores.append((target_face, combined_score))
            
            # Sort by combined score (best first)
            sorted_target_faces = sorted(target_face_scores, key=lambda x: x[1], reverse=True)
            
            for target_face, _ in sorted_target_faces:
                # Apply face swap with paste_back for better blending
                result_img = self.swapper.get(result_img, target_face, source_face, paste_back=True)
                
                # For higher quality, we could add post-processing here
                # like gaussian blur at face boundaries, color matching, etc.
            
            return result_img
    
    def swap_to_bytes(
        self, 
        source_key: str, 
        source_bytes: Union[bytes, BytesIO], 
        target_bytes: Union[bytes, BytesIO],
        format: str = '.jpg'
    ) -> bytes:
        swapped_bgr = self.swap(source_key, source_bytes, target_bytes)
        return self._bgr_to_bytes(swapped_bgr, format)
    
    def clear_cache(self, source_key: Optional[str] = None):
        """Clear face embedding cache"""
        with self._lock:
            if source_key:
                # Clear specific user's cache
                keys_to_remove = [k for k in self._face_cache.keys() if k.startswith(f"{source_key}_")]
                for key in keys_to_remove:
                    del self._face_cache[key]
            else:
                # Clear all cache
                self._face_cache.clear()


def restore_faces_bgr(img_bgr: np.ndarray, upscale: Optional[float] = None) -> np.ndarray:
    """Face restoration function - currently disabled (returns original image)."""
    return img_bgr


def restore_faces_bytes(img_bytes: Union[bytes, BytesIO], upscale: Optional[float] = None) -> bytes:
    # Convert to BGR
    if isinstance(img_bytes, BytesIO):
        img_bytes = img_bytes.getvalue()
    
    nparr = np.frombuffer(img_bytes, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # Restore
    restored_bgr = restore_faces_bgr(img_bgr, upscale)
    
    # Convert back to bytes
    success, encoded_img = cv2.imencode('.jpg', restored_bgr)
    if not success:
        raise ValueError("Failed to encode restored image")
    
    return encoded_img.tobytes() 