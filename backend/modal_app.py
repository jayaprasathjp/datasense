import modal
import json
from pydantic import BaseModel

app = modal.App("datasense")

VLLM_IMAGE = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("git", "build-essential")
    .pip_install("vllm>=0.23.0", "transformers", "huggingface_hub")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "VLLM_USE_FLASHINFER_SAMPLER": "0"})
)

def download_models():
    from huggingface_hub import snapshot_download
    snapshot_download("unsloth/gemma-4-E2B-it")
    snapshot_download("sanjaymalladi/DataSense-Modal-E2B-SFT")
    snapshot_download("google/gemma-4-E2B-it-assistant")

VLLM_IMAGE = VLLM_IMAGE.run_function(download_models)

class ChatRequest(BaseModel):
    messages: list[dict]
    max_new_tokens: int = 512
    temperature: float = 0.2
    stream: bool = False

@app.cls(image=VLLM_IMAGE, gpu="L4", timeout=600, scaledown_window=300, secrets=[modal.Secret.from_name("datasense-secret"), modal.Secret.from_name("huggingface")])
class DataSenseModel:
    @modal.enter()
    def load_model(self):
        from vllm import LLM
        from vllm.lora.request import LoRARequest

        self.llm = LLM(
            model="unsloth/gemma-4-E2B-it",
            max_model_len=4096,
            enable_lora=True,
            max_lora_rank=64,
            enable_prefix_caching=True,
            enforce_eager=True,
            gpu_memory_utilization=0.85,
            dtype="float16",
            speculative_config={
                "model": "google/gemma-4-E2B-it-assistant",
                "num_speculative_tokens": 1,
                "method": "mtp",
            },
        )
        self.lora_req = LoRARequest("datasense_adapter", 1, "sanjaymalladi/DataSense-Modal-E2B-SFT")
        self.tokenizer = self.llm.get_tokenizer()

    @modal.fastapi_endpoint(method="POST")
    def generate(self, req: ChatRequest):
        from vllm import SamplingParams
        from fastapi.responses import StreamingResponse

        prompt = self.tokenizer.apply_chat_template(
            req.messages, tokenize=False, add_generation_prompt=True
        )
        sp = SamplingParams(
            temperature=max(req.temperature, 1e-5),
            max_tokens=req.max_new_tokens,
        )

        if req.stream:
            def event_stream():
                for output in self.llm.generate([prompt], sp, lora_request=self.lora_req, use_tqdm=False, stream=True):
                    if output.outputs[0].text:
                        yield f"data: {json.dumps({'token': output.outputs[0].text})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
            return StreamingResponse(event_stream(), media_type="text/event-stream")
        else:
            outputs = self.llm.generate(
                [prompt], sp, lora_request=self.lora_req, use_tqdm=False
            )
            result = outputs[0].outputs[0].text
            return {
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": result},
                    "finish_reason": "stop",
                }]
            }
