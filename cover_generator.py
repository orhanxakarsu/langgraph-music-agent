"""
Image Generator Agent
=====================
Generates music covers using Google Gemini API.
"""

import os
import uuid
from pathlib import Path
from io import BytesIO
from PIL import Image
from google import genai
from dotenv import load_dotenv

load_dotenv()


class GoogleApi:
    """Google Gemini API wrapper for image generation"""

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            print("Warning: GEMINI_API_KEY not found!")
            self.client = None

    def generate_image(self, prompt: str, image_path: str = None) -> str:
        """
        Generates image based on given prompt.
        
        Args:
            prompt: Image generation prompt (English recommended)
            image_path: File path to save (optional)
            
        Returns:
            Path of saved file
        """
        
        if not self.client:
            raise Exception("Gemini client not initialized")
        
        # Default path
        if not image_path:
            image_id = str(uuid.uuid4())
            image_path = f"artifacts/generated_images/{image_id}.png"
        
        # Create directory
        Path(image_path).parent.mkdir(parents=True, exist_ok=True)
        
        print(f"Generating image...")
        print(f"   Prompt: {prompt[:100]}...")
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-exp-image-generation",
                contents=[prompt],
                config=genai.types.GenerateContentConfig(
                    response_modalities=['TEXT', 'IMAGE']
                )
            )
            
            # Extract image from response
            for part in response.candidates[0].content.parts:
                if part.text is not None:
                    print(f"   Model response: {part.text[:100]}...")
                elif part.inline_data is not None:
                    image = Image.open(BytesIO(part.inline_data.data))
                    image.save(image_path)
                    print(f"   Image saved: {image_path}")
                    return image_path
            
            # If no image found
            raise Exception("No image found in API response")
            
        except Exception as e:
            print(f"   Image generation error: {e}")
            raise


class ImageGeneratorAgent:
    """
    Standalone Image Generator Agent.
    Used by System Supervisor.
    """
    
    def __init__(self):
        self.google_api = GoogleApi()
        self.images_path = "artifacts/generated_images/"
        os.makedirs(self.images_path, exist_ok=True)
    
    def generate_cover(self, description: str, music_style: str = None, music_title: str = None) -> dict:
        """
        Generates music cover.
        
        Args:
            description: Cover description
            music_style: Music style (optional)
            music_title: Music title (optional)
            
        Returns:
            {"success": bool, "image_path": str, "image_id": str, "error": str}
        """
        
        # Create prompt
        prompt = f"Create a minimalist album cover art. "
        
        if music_style:
            prompt += f"Music style: {music_style}. "
        
        if music_title:
            prompt += f"Title inspiration: {music_title}. "
        
        prompt += f"Description: {description}. "
        prompt += "No text on the image. Clean, professional, visually striking."
        
        try:
            cover_id = str(uuid.uuid4())
            image_path = os.path.join(self.images_path, f"{cover_id}.png")
            
            generated_path = self.google_api.generate_image(prompt, image_path)
            
            return {
                "success": True,
                "image_path": generated_path,
                "image_id": cover_id,
                "prompt_used": prompt
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "image_path": None,
                "image_id": None
            }


# Factory function
def create_image_generator():
    return ImageGeneratorAgent()