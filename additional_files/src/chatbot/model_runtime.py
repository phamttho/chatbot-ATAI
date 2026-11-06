"""Small local Transformers runtime, with no remote inference dependency."""
import os
import torch
from transformers import AutoConfig, AutoTokenizer, AutoModelForCausalLM, AutoModelForImageTextToText


class ModelRuntime:
    def __init__(self, model_name, device='auto'):
        torch.set_num_threads(int(os.environ.get('MOVIE_TORCH_THREADS', '4')))
        if device == 'auto':
            device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
        self.device, self.model_name = device, model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        config = AutoConfig.from_pretrained(model_name)
        model_class = AutoModelForImageTextToText if config.model_type == 'qwen3_5' else AutoModelForCausalLM
        if device == 'cuda':
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        else:
            dtype = torch.float32
        self.model = model_class.from_pretrained(model_name, dtype=dtype, attn_implementation='sdpa').to(device).eval()
        self.revision = getattr(config, '_commit_hash', None)
        self.calls = 0

    def generate(self, system, message, max_new_tokens=256):
        self.calls += 1
        prompt = self.tokenizer.apply_chat_template([
            {'role':'system', 'content':system}, {'role':'user', 'content':message}
        ], tokenize=False, add_generation_prompt=True, enable_thinking=False)
        inputs = self.tokenizer(prompt, return_tensors='pt').to(self.device)
        with torch.inference_mode():
            output = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False,
                                         pad_token_id=self.tokenizer.eos_token_id, use_cache=True)
        return self.tokenizer.decode(output[0, inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
