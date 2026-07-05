import os
from google import genai
from google.auth import default

# This will use the GOOGLE_APPLICATION_CREDENTIALS set in the env
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "datasense-gpu-1d8863516c4e.json"

client = genai.Client(
    vertexai=True,
    project="datasense-gpu",
    location="us-central1"
)

try:
    print("Testing us-central1...")
    models = client.models.list()
    for m in models:
        print(m.name)
except Exception as e:
    print(f"Error in us-central1: {e}")

try:
    client_asia = genai.Client(
        vertexai=True,
        project="datasense-gpu",
        location="asia-south1"
    )
    print("\nTesting asia-south1...")
    models = client_asia.models.list()
    for m in models:
        print(m.name)
except Exception as e:
    print(f"Error in asia-south1: {e}")
