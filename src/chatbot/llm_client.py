import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"


class LocalLLM:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        print(f"Loading LLM: {MODEL_NAME}")
        print(f"LLM device: {self.device}")

        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            dtype=torch.float16 if self.device == "cuda" else torch.float32,
        )

        self.model.to(self.device)
        self.model.eval()

        print("LLM loaded.")

    def generate(self, message):
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful movie assistant. "
                    "Only discuss movies and movie-related topics. "
                    "Keep answers concise."
                ),
            },
            {
                "role": "user",
                "content": message,
            },
        ]

        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=100,
                do_sample=False,
            )

        generated = output[0][inputs["input_ids"].shape[1]:]

        return self.tokenizer.decode(
            generated,
            skip_special_tokens=True,
        ).strip()
