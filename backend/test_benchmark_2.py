import sys
import os
sys.path.append(os.getcwd())
from app.services.modal_sandbox import prewarm_sandbox, execute_on_prewarmed_sandbox
from app.services.llm_engine import synthesize_code, synthesize_cpu_code

print('1. synthesizing code...')
gpu_code = synthesize_code('group by region and calculate total revenue', 'data_analysis')
print('GPU code ready')

print('2. prewarming gpu sandbox...')
sb_gpu = prewarm_sandbox('gpu')
print('Sandbox GPU ready:', sb_gpu.object_id)

print('3. executing...')
res = execute_on_prewarmed_sandbox(sb_gpu, gpu_code, 'gpu')
print('Result:', res)
