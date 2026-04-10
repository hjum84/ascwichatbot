import os
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Configure Gemini
api_key = os.getenv("GOOGLE_API_KEY")
print(f"API Key loaded: {api_key[:20]}..." if api_key else "API Key NOT found!")

if api_key:
    genai.configure(api_key=api_key)
    
    # Test with a simple question
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    try:
        response = model.generate_content(
            "Say 'Hello, I am working!' if you can read this.",
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=100,
                temperature=0.3,
            )
        )
        
        print(f"✅ SUCCESS! Gemini Response: {response.text}")
    except Exception as e:
        print(f"❌ ERROR: {e}")
else:
    print("❌ GOOGLE_API_KEY environment variable not set!")
