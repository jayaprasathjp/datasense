import logging
from google import genai
from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize the Gemini client
client = genai.Client(api_key=settings.gemini_api_key)
MODEL_ID = "gemini-2.0-flash"

def synthesize_code(query: str, task_type: str = "data_analysis") -> str:
    """
    Translates a natural language query into pandas code.
    Assumes a pandas DataFrame named `df` exists.
    """
    logger.info(f"Synthesizing code for query: {query}")
    
    prompt = f"""
You are an expert Data Scientist. Write python pandas code to answer the following query.
Assume there is a pre-loaded pandas DataFrame named `df`.
The DataFrame has the following columns: id, order_id, user_id, product_id, sale_price, created_at, status.

Task Type: {task_type}
Query: {query}

Requirements:
1. Output ONLY valid, executable Python code. No markdown formatting blocks like ```python, no explanations.
2. Do NOT import pandas or create the dataframe, just write the data manipulation logic.
3. The final result of the operation MUST be printed to stdout as a dictionary or a JSON string using `print()`. 
   For example, if your final variable is `result_df`, do `print(result_df.to_json(orient='records'))`.
   If it's a series, do `print(result.to_json())`.
   If it's a single value, do `print({{"result": final_value}})`.
   This is critical so we can parse the output from stdout.
"""
    
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt
    )
    
    code = response.text.strip()
    if code.startswith("```python"):
        code = code[9:]
    elif code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
        
    return code.strip()

def fix_code(original_code: str, error_message: str) -> str:
    """
    Asks Gemini to fix the pandas code based on an execution error.
    """
    logger.info("Sending code to Gemini for error fixing...")
    
    prompt = f"""
The following pandas code was executed but resulted in an error. 
Please fix the code. Assume there is a pre-loaded pandas DataFrame named `df`.
Ensure the final output is printed to stdout using `print()`.

Original Code:
{original_code}

Error Message:
{error_message}

Output ONLY the corrected valid Python code. No markdown, no explanations.
"""
    
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt
    )
    
    code = response.text.strip()
    if code.startswith("```python"):
        code = code[9:]
    elif code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
        
    return code.strip()
