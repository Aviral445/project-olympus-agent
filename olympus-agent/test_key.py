import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

print("🔄 Loading .env file...")
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("❌ ERROR: Could not find GEMINI_API_KEY inside your .env file!")
    print("Please check that your file is named exactly '.env' and contains your key.")
    exit(1)

print(f"🔑 Key found in .env (starts with: {api_key[:6]}...)")
print("📡 Connecting to Google Gemini API...")

try:
    # Initialize the Gemini model using LangChain
    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash", google_api_key=api_key)
    
    # Send a simple ping message
    response = llm.invoke("Hello Gemini! If you can hear me, respond with the word 'CONNECTED'.")
    
    print("\n--- API RESPONSE ---")
    # This handles both strings and lists safely
    if isinstance(response.content, list):
        print(response.content[0].get("text", response.content))
    else:
        print(response.content)
    print("--------------------")
    print("🎉 SUCCESS! Your API key is 100% working. We are clear for takeoff!")

except Exception as e:
    print("\n❌ API CONNECTION FAILED!")
    print(f"Error details: {str(e)}")