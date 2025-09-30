import google.generativeai as genai
from django.conf import settings


class AIService:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set in settings.")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel("gemini-pro")

    def get_gemini_response(self, message: str) -> str:
        """
        Sends a message to the Gemini API and gets a response.
        """
        try:
            response = self.model.generate_content(message)
            return response.text
        except Exception as e:
            # In a real application, you'd want to log this error.
            print(f"Error calling Gemini API: {e}")
            return "Sorry, I'm having trouble thinking right now."


# Instantiate the service for easy import
ai_service = AIService()
