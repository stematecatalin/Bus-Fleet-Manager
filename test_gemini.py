import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("SKIP: GEMINI_API_KEY not found in environment.")
else:
    print(f"Testing API Key: {api_key[:10]}...{api_key[-5:]}")
    genai.configure(api_key=api_key)

try:
    print("Listing available models...")
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
    
    # Încercăm cu gemini-pro (cel mai comun model stabil)
    print("\nTrying with gemini-pro...")
    model = genai.GenerativeModel('gemini-pro')
    response = model.generate_content("Salut, ești activ?")
    print("SUCCESS!")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"FAILED: {e}")
