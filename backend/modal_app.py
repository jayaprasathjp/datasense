import modal
from pydantic import BaseModel

app = modal.App("datasense-llm")

# We build a Debian image with Python 3.10, install git, and pip install the required ML packages.
# We then specifically install unsloth from its github repo to ensure compatibility.
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("git", "build-essential")
    .pip_install(
        "torch==2.3.0",
        "transformers",
        "accelerate",
        "bitsandbytes",
        "peft",
        "scipy",
        "fastapi[standard]"
    )
    .pip_install("unsloth")
)

class RequestBody(BaseModel):
    system_prompt: str
    user_prompt: str

# Use a T4 GPU and set a timeout of 10 minutes (to allow the model to download/load on cold boot)
@app.cls(image=image, gpu="T4", timeout=600)
class DataSenseModel:
    @modal.enter()
    def load_model(self):
        """This runs once when the container boots, storing the model in GPU memory."""
        from unsloth import FastLanguageModel
        
        BASE_MODEL = "unsloth/gemma-4-E2B-it"
        LORA_ADAPTER = "sanjaymalladi/DataSense-Modal-E2B-SFT"
        MAX_SEQ_LEN = 4096

        print(f"Loading Base Model ({BASE_MODEL}) in 4-bit...")
        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            model_name=BASE_MODEL,
            max_seq_length=MAX_SEQ_LEN,
            dtype=None,
            load_in_4bit=True,
        )
        
        print(f"Attaching LoRA Adapter ({LORA_ADAPTER})...")
        self.model.load_adapter(LORA_ADAPTER)
        
        # Prepare for extremely fast inference
        FastLanguageModel.for_inference(self.model)
        print("Model is ready for inference!")

    @modal.fastapi_endpoint(method="POST")
    def generate(self, req: RequestBody):
        """This exposes a POST endpoint that takes the prompts and returns the LLM response."""
        messages = [
            {"role": "system", "content": req.system_prompt},
            {"role": "user", "content": req.user_prompt},
        ]
        
        # Format the chat template exactly as Gemma expects
        inputs = self.tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
        ).to(self.model.device)

        # Generate tokens
        out = self.model.generate(
            input_ids=inputs,
            max_new_tokens=512,
            temperature=0.2,
            do_sample=True,
            pad_token_id=self.tokenizer.eos_token_id,
        )
        
        # Decode only the newly generated tokens
        new_tokens = out[0][inputs.shape[1]:]
        text = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        
        return {"result": text}
