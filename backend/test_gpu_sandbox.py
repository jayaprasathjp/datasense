import modal, threading, time

print('Creating GPU sandbox with RAPIDS image...')
print('(First run will take 10-15 min to build image - watch for output below)')

gpu_image = (
    modal.Image.debian_slim()
    .pip_install(
        'cudf-cu12',
        'cuml-cu12', 
        'pyarrow',
        'numpy',
        extra_index_url='https://pypi.nvidia.com',
    )
)

app = modal.App.lookup('datasense-sandbox', create_if_missing=True)

with modal.enable_output():
    sb = modal.Sandbox.create(
        app=app,
        image=gpu_image,
        gpu='T4',
        timeout=1800,
    )

print(f'Sandbox created: {sb.object_id}')

test_code = b'''
import sys
print("Python running inside sandbox!", flush=True)

try:
    import cudf
    print(f"cuDF version: {cudf.__version__}", flush=True)
    df = cudf.DataFrame({'a': [1,2,3,4,5], 'b': [10,20,30,40,50]})
    result = df.groupby('a')['b'].sum()
    print(f"Test groupby result: {result.to_pandas().to_dict()}", flush=True)
    print("GPU cuDF TEST PASSED!", flush=True)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr, flush=True)
    sys.exit(1)
'''

print('Executing test code...')
p = sb.exec('python', '-u', '-')
p.stdin.write(test_code)
p.stdin.write_eof()
p.stdin.drain()

def stream_out():
    for line in p.stdout:
        print('[STDOUT]', line, end='', flush=True)

def stream_err():
    for line in p.stderr:
        print('[STDERR]', line, end='', flush=True)

t1 = threading.Thread(target=stream_out, daemon=True)
t2 = threading.Thread(target=stream_err, daemon=True)
t1.start(); t2.start()

rc = p.wait()
t1.join(timeout=10); t2.join(timeout=10)

print(f'Process exited with code: {rc}')
sb.terminate()
print('Sandbox terminated. Test complete.')
