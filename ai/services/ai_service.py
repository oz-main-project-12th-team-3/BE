import google.generativeai as genai
from django.conf import settings

# Configure the Gemini API key from Django settings
try:
    gemini_api_key = settings.GEMINI_API_KEY
    if not gemini_api_key:
        # This will be caught by the except block
        raise ValueError("GEMINI_API_KEY is not set in settings.")
    genai.configure(api_key=gemini_api_key)
    # A simple flag to check if the service is available
    IS_GEMINI_CONFIGURED = True
except (AttributeError, ValueError) as e:
    print(f"WARNING: Gemini API not configured. {e}")
    IS_GEMINI_CONFIGURED = False


def get_gemini_response(prompt: str) -> str:
    """
    Gets a response from the Gemini Pro model for a given prompt.
    Returns a string with the AI's response or an error message.
    """
    if not IS_GEMINI_CONFIGURED:
        return (
            "AI service is not configured. "
            "Please set the GEMINI_API_KEY in your environment."
        )

    try:
        # Initialize the model
        model = genai.GenerativeModel("gemini-pro")
        # Generate content
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        # Handle potential API errors gracefully
        print(f"An error occurred with the Gemini API: {e}")
        return "Sorry, I encountered an error while processing your request."
